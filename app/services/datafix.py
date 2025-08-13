# app/services/datafix.py
from __future__ import annotations
from typing import List, Tuple, Optional
import json, os, requests
from sqlalchemy import text
from app.db.session import SessionLocal
from app.core.config import settings

def _schedule_url(season: int) -> str:
    return f"{settings.ergast_url}/{season}.json?limit=1000"

def _load_schedule(season: int, local_file: Optional[str]) -> dict:
    # 1) Try live (Jolpi/Ergast mirror from .env)
    try:
        resp = requests.get(_schedule_url(season), timeout=20)
        resp.raise_for_status()
        return resp.json()
    except Exception:
        pass
    # 2) Local fallbacks
    if local_file and os.path.exists(local_file):
        with open(local_file, "r", encoding="utf-8") as f:
            return json.load(f)
    fallback_path = f"app/data/ergast_{season}.json"
    if os.path.exists(fallback_path):
        with open(fallback_path, "r", encoding="utf-8") as f:
            return json.load(f)
    raise RuntimeError(f"Could not load schedule for {season} from {settings.ergast_base} or local cache.")

def backfill_circuit_names(season: int, local_file: Optional[str] = None) -> List[Tuple[int, str]]:
    data = _load_schedule(season, local_file)
    races = data.get("MRData", {}).get("RaceTable", {}).get("Races", [])
    updated: List[Tuple[int, str]] = []
    with SessionLocal() as db:
        for r in races:
            try:
                rnd = int(r.get("round"))
            except Exception:
                continue
            circuit_name = (r.get("Circuit") or {}).get("circuitName")
            if not circuit_name:
                continue
            res = db.execute(
                text("""
                    UPDATE races
                    SET circuit = :circuit
                    WHERE year = :season AND round = :round
                    RETURNING id
                """),
                {"circuit": circuit_name, "season": season, "round": rnd},
            )
            if res.rowcount:
                updated.append((rnd, circuit_name))
        db.commit()
    return sorted(updated, key=lambda x: x[0])
