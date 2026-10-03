"""End-to-end smoke test. Start the server first:  FOC_SPEED=10 uvicorn app.main:app --port 8000
Then:  python smoke_test.py"""
import asyncio, json, urllib.request
import websockets

BASE, WS = "http://127.0.0.1:8000", "ws://127.0.0.1:8000"


def http(method, path, body=None):
    req = urllib.request.Request(BASE + path, method=method, data=json.dumps(body or {}).encode(),
                                 headers={"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(req))


async def trainee(role, got, stop):
    async with websockets.connect(f"{WS}/ws/{role}") as ws:
        await ws.recv()  # init
        while not stop.is_set():
            try:
                m = json.loads(await asyncio.wait_for(ws.recv(), 0.5))
            except asyncio.TimeoutError:
                continue
            if m["type"] == "report":
                got[role].append(m["report"])
                if m["report"]["pos"] and len(got[role]) == 2:   # act on the 2nd positional report
                    await ws.send(json.dumps({"type": "decision", "action": "engage",
                                              "target": m["report"]["pos"], "rationale": "latest sighting"}))


async def main():
    http("POST", "/api/reset")
    http("POST", "/api/rules/alpha", {"delay": 6, "jitter": 2, "dropout": 0.3, "conflict": 0.6, "spoof": 0.3})
    got, stop = {"alpha": [], "bravo": []}, asyncio.Event()
    tasks = [asyncio.create_task(trainee(r, got, stop)) for r in got]
    await asyncio.sleep(0.5)
    http("POST", "/api/start")
    while http("GET", "/api/state")["status"] != "finished":
        await asyncio.sleep(0.5)
    stop.set(); await asyncio.gather(*tasks)
    aar = http("GET", "/api/aar")
    print("summary:", json.dumps(aar["summary"]))
    for d in aar["decisions"]:
        print(d["role"], d["action"], d["target"], "| believed", d["believed_enemy"], "| true", d["true_enemy"], "|", d["label"])
    a, b = aar["summary"]["alpha"], aar["summary"]["bravo"]
    assert b["dropped"] == b["conflicting"] == b["spoofed"] == 0, "bravo link should be clean"
    assert a["mean_delay_s"] and a["mean_delay_s"] > b["mean_delay_s"], "alpha link should be slower"
    assert len(aar["decisions"]) >= 1
    print("SMOKE TEST PASSED")

asyncio.run(main())