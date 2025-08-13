from typing import List, Dict, Any
from datetime import datetime, timedelta

# Temporary in-memory data; replace with DB/FastF1
def get_upcoming_race() -> Dict[str, Any]:
    # Dummy upcoming race one week from now
    return {
        "id": 2025_14,  # year_round
        "year": 2025,
        "round": 14,
        "grand_prix": "Example GP",
        "circuit": "Example Circuit",
        "date": (datetime.utcnow() + timedelta(days=7)).date().isoformat(),
    }

def get_grid_for_race(race_id: int):
    # Dummy 5-car grid
    return [
        {"position": 1, "driver_id": 44, "driver_code": "HAM", "team": "Mercedes"},
        {"position": 2, "driver_id": 1, "driver_code": "VER", "team": "Red Bull"},
        {"position": 3, "driver_id": 16, "driver_code": "LEC", "team": "Ferrari"},
        {"position": 4, "driver_id": 4, "driver_code": "NOR", "team": "McLaren"},
        {"position": 5, "driver_id": 63, "driver_code": "RUS", "team": "Mercedes"},
    ]
