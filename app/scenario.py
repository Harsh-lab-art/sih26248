"""One sample scenario. Positions are on a 100x100 grid. Replace/extend via the same shape."""

SCENARIO = {
    "id": "delta-1",
    "title": "Sector Delta: armoured thrust under EW pressure",
    "map": {"w": 100, "h": 100},
    "duration": 100,  # simulated seconds
    "roles": {
        "alpha": {"unit": "A-Coy (Infantry)", "pos": [15, 82]},
        "bravo": {"unit": "B-Coy (Mech Inf)", "pos": [82, 86]},
    },
    # Ground-truth events. 'tpl' is formatted with the position when one exists.
    "events": [
        {"t": 3,  "fact": "enemy_armour", "audience": ["alpha", "bravo"], "pos": [50, 38], "tpl": "Enemy armour column sighted at grid {x}/{y}"},
        {"t": 18, "fact": "enemy_armour", "audience": ["alpha", "bravo"], "pos": [55, 44], "tpl": "Armour column moving SE, now at grid {x}/{y}"},
        {"t": 28, "fact": "ew",           "audience": ["alpha"],          "pos": None,      "tpl": "EW cell: jamming detected on UHF net"},
        {"t": 38, "fact": "enemy_armour", "audience": ["alpha", "bravo"], "pos": [62, 52], "tpl": "Armour column now at grid {x}/{y}"},
        {"t": 48, "fact": "supply",       "audience": ["bravo"],          "pos": None,      "tpl": "B-Coy fuel at 35 percent, resupply needed"},
        {"t": 58, "fact": "enemy_armour", "audience": ["alpha", "bravo"], "pos": [70, 60], "tpl": "Armour column now at grid {x}/{y}"},
        {"t": 75, "fact": "enemy_armour", "audience": ["alpha", "bravo"], "pos": [76, 70], "tpl": "Armour column now at grid {x}/{y}"},
    ],
}


def enemy_truth(t):
    """True enemy position at sim time t (step function over scripted sightings)."""
    pos = None
    for e in SCENARIO["events"]:
        if e["fact"] == "enemy_armour" and e["t"] <= t:
            pos = e["pos"]
    return pos