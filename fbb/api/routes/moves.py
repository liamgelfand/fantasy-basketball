from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from ...engine import Engine
from ...espn import PlayerInfo, TeamInfo
from .. import presenters, schemas
from ..deps import EngineDep

router = APIRouter(tags=["moves"])


def _from_roster(team: TeamInfo, names: list[str]) -> list[PlayerInfo]:
    by_name = {p.name.lower(): p for p in team.roster}
    missing = [n for n in names if n.lower() not in by_name]
    if missing:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"Not on {team.name}: {', '.join(missing)}")
    return [by_name[n.lower()] for n in names]


def _lookup(engine: Engine, names: list[str]) -> list[PlayerInfo]:
    found = [(n, engine.data.find_player(n)) for n in names]
    missing = [n for n, p in found if p is None]
    if missing:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"Couldn't find: {', '.join(missing)}")
    return [p for _, p in found]


@router.post("/simulate", response_model=schemas.MoveResultOut)
def simulate(body: schemas.SimulationRequest, engine: EngineDep):
    if not body.add and not body.drop:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Pick at least one player to add or drop.")
    if engine.projection.opponent is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "No active matchup to simulate against.")
    drops = _from_roster(engine.data.my_team, body.drop)
    adds = _lookup(engine, body.add)
    return presenters.move_result(engine, engine.simulate(adds, drops))


@router.post("/trades/evaluate", response_model=schemas.TradeResult)
def evaluate_trade(body: schemas.TradeRequest, engine: EngineDep):
    partner = engine.data.teams.get(body.partner_id)
    if partner is None or partner.id == engine.data.my_team_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"No trade partner with id {body.partner_id}")
    give = _from_roster(engine.data.my_team, body.give)
    get = _from_roster(partner, body.get)
    return presenters.trade(engine, give, get)
