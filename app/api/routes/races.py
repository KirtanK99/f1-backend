from fastapi import APIRouter, HTTPException
from typing import List
from app.schemas.races import Race, GridEntry
from app.services import races as race_service

router = APIRouter()

@router.get("/upcoming", response_model=Race)
def upcoming_race():
    return race_service.get_upcoming_race()

@router.get("/{race_id}/grid", response_model=List[GridEntry])
def race_grid(race_id: int):
    data = race_service.get_grid_for_race(race_id)
    if not data:
        raise HTTPException(404, "Grid not found")
    return data
