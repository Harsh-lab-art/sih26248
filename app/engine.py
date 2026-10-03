"""Simulation engine: true world state, event scheduler, per-trainee delivery, decision logging, scoring."""
import asyncio
import math
import os
import random
import time

from .degradation import LinkRules, degrade
from .scenario import SCENARIO, enemy_truth

SPEED = float(os.environ.get("FOC_SPEED", "1"))   # >1 runs the clock faster (handy for tests)
SOUND_RADIUS = 12.0                                  # "close enough" radius for a target decision
TRAINEES = list(SCENARIO["roles"].keys())


def dist(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


class Hub:
    """Tracks websocket connections per role."""

    def __init__(self):
        self.conns = {}

    def add(self, role, ws):
        self.conns.setdefault(role, set()).add(ws)

    def remove(self, role, ws):
        self.conns.get(role, set()).discard(ws)

    async def send(self, role, msg):
        for ws in list(self.conns.get(role, ())):
            try:
                await ws.send_json(msg)
            except Exception:
                self.remove(role, ws)

    async def broadcast(self, msg):
        for role in list(self.conns):
            await self.send(role, msg)


class Exercise:
    def __init__(self, seed=None):
        self.seed = seed
        self.hub = Hub()
        self.tasks = set()
        self.reset()

    # ---------- lifecycle ----------
    def reset(self):
        for t in list(self.tasks):
            t.cancel()
        self.tasks = set()
        self.status = "idle"            # idle | running | finished
        self.t0 = None
        self.final_t = 0.0
        self.rng = random.Random(self.seed)
        self.rules = {r: LinkRules() for r in TRAINEES}
        self.reports, self.deliveries, self.decisions = [], [], []
        self.shown = {r: [] for r in TRAINEES}   # what each trainee has actually seen
        self.belief = {r: None for r in TRAINEES}
        self.next_event = 0

    def now(self):
        if self.status == "running":
            return (time.monotonic() - self.t0) * SPEED
        return self.final_t

    async def start(self):
        if self.status == "running":
            return
        self.reset()
        self.status = "running"
        self.t0 = time.monotonic()
        await self.hub.broadcast({"type": "state", "status": "running"})
        self._spawn(self._loop())

    def _spawn(self, coro):
        task = asyncio.create_task(coro)
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)

    async def _loop(self):
        last_tick = -1
        events = SCENARIO["events"]
        while self.status == "running":
            t = self.now()
            while self.next_event < len(events) and events[self.next_event]["t"] <= t:
                await self._fire(events[self.next_event])
                self.next_event += 1
            if int(t) != last_tick:
                last_tick = int(t)
                await self.hub.broadcast({"type": "tick", "t": round(t, 1)})
                await self.hub.send("instructor", {"type": "truth", "t": round(t, 1), "enemy": enemy_truth(t)})
            if t >= SCENARIO["duration"]:
                await asyncio.sleep(5 / SPEED)  # let in-flight messages land
                self.final_t = self.now()
                self.status = "finished"
                await self.hub.broadcast({"type": "state", "status": "finished"})
                return
            await asyncio.sleep(0.1)

    # ---------- events and degradation ----------
    async def _fire(self, ev):
        report = {"id": f"R{len(self.reports) + 1}", "t": ev["t"], "fact": ev["fact"], "pos": ev["pos"],
                  "tpl": ev["tpl"], "text": ev["tpl"].format(x=(ev["pos"] or [0, 0])[0], y=(ev["pos"] or [0, 0])[1])}
        self.reports.append(report)
        for role in ev["audience"]:
            for status, delay, shown in degrade(report, self.rules[role], self.rng):
                rec = {"report_id": report["id"], "role": role, "status": status, "sent_t": ev["t"],
                       "delay_s": None if delay is None else round(delay, 2), "delivered_t": None,
                       "truth_text": report["text"], "shown_text": None if shown is None else shown["text"]}
                self.deliveries.append(rec)
                if shown is None:
                    await self.hub.send("instructor", {"type": "delivery", **rec})
                else:
                    self._spawn(self._deliver(rec, shown, delay))

    async def _deliver(self, rec, shown, delay):
        await asyncio.sleep(delay / SPEED)
        t = round(self.now(), 1)
        rec["delivered_t"] = t
        view = {"id": shown["id"], "sent_t": shown["t"], "recv_t": t, "pos": shown["pos"], "text": shown["text"]}
        self.shown[rec["role"]].append({**view, "fact": shown["fact"]})
        if shown["fact"] == "enemy_armour" and shown["pos"]:
            self.belief[rec["role"]] = {"pos": shown["pos"], "recv_t": t}   # trainee's working belief = latest arrival
        await self.hub.send(rec["role"], {"type": "report", "report": view})
        await self.hub.send("instructor", {"type": "delivery", **rec})

    # ---------- instructor controls ----------
    async def set_rules(self, link, params):
        self.rules[link].update(**params)
        await self.hub.send("instructor", {"type": "rules", "rules": self.rules_dict()})

    def rules_dict(self):
        return {k: v.as_dict() for k, v in self.rules.items()}

    # ---------- decisions and scoring ----------
    def _uncertainty(self, role, t):
        pts = [r["pos"] for r in self.shown[role] if r["fact"] == "enemy_armour" and r["pos"] and t - r["recv_t"] <= 20]
        spread = max((dist(a, b) for a in pts for b in pts), default=0.0)
        return round(min(1.0, spread / 30.0), 2)

    @staticmethod
    def _label(sound, good):
        if sound is None:
            return "n/a"
        return {(True, True): "sound and good outcome",
                (True, False): "sound given what was known (bad information)",
                (False, True): "lucky: not supported by what was known",
                (False, False): "unsound and poor outcome"}[(sound, good)]

    async def decide(self, role, d):
        if self.status != "running":
            return {"type": "ack", "ok": False, "error": "exercise is not running"}
        t = self.now()
        target = d.get("target")
        action = str(d.get("action", "hold"))[:30]
        b, truth = self.belief[role], enemy_truth(t)
        bd = dist(target, b["pos"]) if (target and b) else None
        td = dist(target, truth) if (target and truth) else None
        scored = action in ("move", "engage") and target is not None
        sound = (bd is not None and bd <= SOUND_RADIUS) if scored else None
        good = (td is not None and td <= SOUND_RADIUS) if scored else None
        rec = {"id": len(self.decisions) + 1, "t": round(t, 1), "role": role, "action": action, "target": target,
               "rationale": str(d.get("rationale", ""))[:300],
               "view_snapshot": [{k: r[k] for k in ("id", "sent_t", "recv_t", "text")} for r in self.shown[role]],
               "believed_enemy": b["pos"] if b else None, "true_enemy": truth,
               "belief_distance": None if bd is None else round(bd, 1),
               "truth_distance": None if td is None else round(td, 1),
               "uncertainty": self._uncertainty(role, t), "label": self._label(sound, good)}
        self.decisions.append(rec)
        await self.hub.send("instructor", {"type": "decision", **{k: v for k, v in rec.items() if k != "view_snapshot"}})
        return {"type": "ack", "ok": True, "decision_id": rec["id"], "t": rec["t"]}

    # ---------- after-action review ----------
    def aar(self):
        summary = {}
        for r in TRAINEES:
            rows = [x for x in self.deliveries if x["role"] == r]
            got = [x["delay_s"] for x in rows if x["delay_s"] is not None]
            summary[r] = {"reports_sent": len(rows), "dropped": sum(x["status"] == "dropped" for x in rows),
                          "conflicting": sum(x["status"] == "conflicting" for x in rows),
                          "spoofed": sum(x["status"] == "spoofed" for x in rows),
                          "mean_delay_s": round(sum(got) / len(got), 2) if got else None}
        return {"scenario": SCENARIO["title"], "status": self.status, "duration_s": round(self.final_t or self.now(), 1),
                "summary": summary, "decisions": self.decisions, "deliveries": self.deliveries}

    def init_msg(self, role):
        base = {"type": "init", "role": role, "status": self.status, "title": SCENARIO["title"], "map": SCENARIO["map"],
                "units": {r: {"unit": v["unit"], "pos": v["pos"]} for r, v in SCENARIO["roles"].items()}}
        if role == "instructor":
            base["rules"] = self.rules_dict()
        else:
            base["own"] = SCENARIO["roles"][role]
            base["reports"] = [{k: r[k] for k in ("id", "sent_t", "recv_t", "pos", "text")} for r in self.shown[role]]
        return base