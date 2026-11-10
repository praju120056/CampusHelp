import asyncio
import json
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Location, User
from app.routers.deps import STAFF, TICKET_STAFF
from app.schemas.serializers import location_dict, ticket_summary
from app.services import campus_map
from app.services.auth import decode_token, require_role
from app.services.events import CHANNELS, broker

router = APIRouter(tags=["map"])

# Which roles may listen to which live stream.
STREAM_ROLES = {"tickets": set(STAFF), "logs": {"hod", "faculty"}, "adjustments": {"hod", "faculty"}}


@router.get("/map/floors")
def floors(user: User = Depends(require_role(*TICKET_STAFF)), db: Session = Depends(get_db)):
    return campus_map.floors(db)


@router.get("/map/summary")
def summary(user: User = Depends(require_role(*TICKET_STAFF)), db: Session = Depends(get_db)):
    return campus_map.summary(db)


@router.get("/map/{block}/{floor}")
def floor_map(
    block: str,
    floor: int,
    category: Optional[str] = None,
    status: Optional[str] = None,
    user: User = Depends(require_role(*TICKET_STAFF)),
    db: Session = Depends(get_db),
):
    return campus_map.floor_map(db, block, floor, category, status)


@router.get("/locations")
def list_locations(user: User = Depends(require_role(*TICKET_STAFF)), db: Session = Depends(get_db)):
    locs = db.query(Location).order_by(Location.block, Location.floor, Location.side, Location.sort_order).all()
    return [location_dict(loc) | {"qr_url": campus_map.qr_url(loc.code)} for loc in locs]


@router.get("/locations/{code}/tickets")
def location_tickets(code: str, user: User = Depends(require_role(*TICKET_STAFF)), db: Session = Depends(get_db)):
    loc = db.query(Location).filter(Location.code == code).first()
    if loc is None:
        raise HTTPException(status_code=404, detail="Unknown location")
    history = campus_map.location_history(db, loc)
    return {
        "location": location_dict(loc, with_assets=True),
        "open": [ticket_summary(t) for t in history["open"]],
        "closed": [ticket_summary(t) for t in history["closed"]],
    }


@router.get("/stream/{channel}")
async def stream(channel: str, request: Request, token: str = Query(...)):
    """Server-Sent Events. EventSource cannot send headers, so the JWT comes as ?token=."""
    if channel not in CHANNELS:
        raise HTTPException(status_code=404, detail="Unknown stream")
    payload = decode_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Please log in")
    if payload.get("role") not in STREAM_ROLES[channel]:
        raise HTTPException(status_code=403, detail="Not allowed for your role")

    queue = broker.subscribe(channel)

    async def events():
        try:
            yield "retry: 3000\n\n"
            yield "event: hello\ndata: {}\n\n"
            while True:
                if await request.is_disconnected():
                    break
                try:
                    message = await asyncio.wait_for(queue.get(), timeout=15)
                    yield f"event: {message['type']}\ndata: {json.dumps(message['data'])}\n\n"
                except asyncio.TimeoutError:
                    yield ": keep-alive\n\n"
        finally:
            broker.unsubscribe(channel, queue)

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"},
    )
