from pathlib import Path

from fastapi import Body, FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse

from .engine import TRAINEES, Exercise

app = FastAPI(title="Fog-of-Command prototype")
ex = Exercise()
STATIC = Path(__file__).resolve().parent.parent / "static"
ROLES = TRAINEES + ["instructor"]


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


@app.get("/api/state")
def state():
    return {"status": ex.status, "t": round(ex.now(), 1), "rules": ex.rules_dict()}


@app.post("/api/start")
async def start():
    await ex.start()
    return {"status": ex.status}


@app.post("/api/reset")
async def reset():
    ex.reset()
    await ex.hub.broadcast({"type": "state", "status": "idle"})
    return {"status": ex.status}


@app.post("/api/rules/{link}")
async def rules(link: str, params: dict = Body(...)):
    if link not in ex.rules:
        raise HTTPException(404, "unknown link")
    await ex.set_rules(link, params)
    return ex.rules[link].as_dict()


@app.get("/api/aar")
def aar():
    return ex.aar()


@app.websocket("/ws/{role}")
async def ws_endpoint(ws: WebSocket, role: str):
    if role not in ROLES:
        await ws.close(code=4000)
        return
    await ws.accept()
    ex.hub.add(role, ws)
    try:
        await ws.send_json(ex.init_msg(role))
        while True:
            m = await ws.receive_json()
            if m.get("type") == "decision" and role in TRAINEES:
                await ws.send_json(await ex.decide(role, m))
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        ex.hub.remove(role, ws)