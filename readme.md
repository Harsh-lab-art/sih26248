# Fog-of-Command (SIH26248 prototype)

Command-post trainer where each trainee sees a *degraded* view (delay, dropout, conflicting and spoofed reports) of a true world state,
and every decision is logged with what the trainee could have known, then assessed in an after-action review.

## Run
    pip install -r requirements.txt
    uvicorn app.main:app --reload --port 8000
Open http://localhost:8000 in three tabs: Instructor, Trainee Alpha, Trainee Bravo. Instructor presses Start.

## Layout
- `app/scenario.py`     sample scenario (units, scripted ground-truth events)
- `app/degradation.py`  delay / dropout / conflict / spoof pipeline
- `app/engine.py`       clock, event scheduler, delivery, decision log, belief tracking, AAR
- `app/main.py`         REST + WebSocket API
- `static/index.html`   trainee UI, instructor console, AAR view (no build step)
- `smoke_test.py`       end-to-end check (run with `FOC_SPEED=10` for a fast clock)

State is in memory for now. Next: PostgreSQL persistence, Redis queue, scenario files, PDF AAR export.