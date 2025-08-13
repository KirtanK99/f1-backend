from pydantic import BaseModel
from typing import Optional, List

class Race(BaseModel):
    id: int
    year: int
    round: int
    grand_prix: str
    circuit: str
    date: str  # ISO date for now

class GridEntry(BaseModel):
    position: int
    driver_id: int
    driver_code: str
    team: str

class Prediction(BaseModel):
    driver_id: int
    driver_code: str
    p_win: float
    p_podium: float
