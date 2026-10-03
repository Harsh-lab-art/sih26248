"""Information degradation layer: turns one ground-truth report into what a recipient actually receives."""
from dataclasses import dataclass, asdict

LIMITS = {"delay": (0, 30), "jitter": (0, 10), "dropout": (0, 1), "conflict": (0, 1), "spoof": (0, 1)}


@dataclass
class LinkRules:
    delay: float = 0.5     # mean delivery delay, sim seconds
    jitter: float = 0.3    # +/- uniform jitter on the delay
    dropout: float = 0.0   # probability the report is lost
    conflict: float = 0.0  # probability a contradictory second report also arrives
    spoof: float = 0.0     # probability a fabricated report also arrives

    def update(self, **kw):
        for k, v in kw.items():
            if k in LIMITS:
                lo, hi = LIMITS[k]
                setattr(self, k, max(lo, min(hi, float(v))))

    def as_dict(self):
        return asdict(self)


def _clamp(v, lo=2, hi=98):
    return max(lo, min(hi, v))


def _variant(report, pos, suffix):
    v = dict(report)
    v["id"] = report["id"] + suffix
    v["pos"] = [round(pos[0]), round(pos[1])]
    v["text"] = report["tpl"].format(x=v["pos"][0], y=v["pos"][1])
    return v


def degrade(report, rules, rng):
    """Return a list of (status, delay_s, shown). status: delivered|dropped|conflicting|spoofed."""
    if rng.random() < rules.dropout:
        return [("dropped", None, None)]

    def d():
        return max(0.0, rules.delay + rng.uniform(-rules.jitter, rules.jitter))

    out = [("delivered", d(), dict(report))]
    if report.get("pos"):
        if rng.random() < rules.conflict:
            p = [_clamp(report["pos"][i] + rng.choice([-1, 1]) * rng.uniform(15, 28)) for i in (0, 1)]
            out.append(("conflicting", d() + rng.uniform(0.5, 2.0), _variant(report, p, "c")))
        if rng.random() < rules.spoof:
            p = [rng.uniform(5, 95), rng.uniform(5, 65)]
            out.append(("spoofed", d() + rng.uniform(0.5, 3.0), _variant(report, p, "s")))
    return out