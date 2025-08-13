from typing import List, Optional
from pydantic import BaseModel

class RaceWin(BaseModel):
    race_id: int
    round: int
    date: str                 # ISO date string from DB; fine for now
    grand_prix: str
    country: Optional[str] = None
    location: Optional[str] = None
    circuit: Optional[str] = None

class WinsRacesResponse(BaseModel):
    driver: str
    season: int
    wins_count: int
    races: List[RaceWin]

class DriverRow(BaseModel):
    code: str
    name: str
    team: Optional[str] = None
    points: float
    wins: int
    podiums: int

class DriversLeaderboardResponse(BaseModel):
    season: int
    count: int
    drivers: List[DriverRow]

class ConstructorRow(BaseModel):
    team: str
    points: float
    wins: int
    podiums: int

class ConstructorsLeaderboardResponse(BaseModel):
    season: int
    count: int
    constructors: List[ConstructorRow]
