import os
import math
import argparse
import pandas as pd
from datetime import datetime, timezone
from sqlalchemy import create_engine, text
import fastf1

CACHE_DIR = ".fastf1_cache"
os.makedirs(CACHE_DIR, exist_ok=True)
fastf1.Cache.enable_cache(CACHE_DIR)

DB_URL = os.getenv("DATABASE_URL")
engine = create_engine(DB_URL)

def to_ms(td):
    if pd.isna(td):
        return None
    # FastF1 gives a pandas.Timedelta for race time; convert to ms
    try:
        return int(td.total_seconds() * 1000)
    except Exception:
        return None

def upsert_team(conn, name, country=None):
    r = conn.execute(text("""
        INSERT INTO teams (name, country)
        VALUES (:name, :country)
        ON CONFLICT (name) DO UPDATE SET country = EXCLUDED.country
        RETURNING id
    """), {"name": name, "country": country}).mappings().first()
    return r["id"]

def upsert_driver(conn, code, name, team_id, nationality=None):
    # code is unique in your schema
    r = conn.execute(text("""
        INSERT INTO drivers (code, name, team_id, nationality)
        VALUES (:code, :name, :team_id, :nationality)
        ON CONFLICT (code) DO UPDATE SET
          name = EXCLUDED.name,
          team_id = EXCLUDED.team_id,
          nationality = COALESCE(EXCLUDED.nationality, drivers.nationality)
        RETURNING id
    """), {"code": code, "name": name, "team_id": team_id, "nationality": nationality}).mappings().first()
    return r["id"]

def upsert_race(conn, year, round_no, name, country=None, location=None, grand_prix=None, circuit=None, date_str=None):
    r = conn.execute(text("""
        INSERT INTO races (name, country, location, year, round, grand_prix, circuit, date)
        VALUES (:name, :country, :location, :year, :round, :grand_prix, :circuit, :date)
        ON CONFLICT ON CONSTRAINT unique_races_year_round DO UPDATE SET
          name = EXCLUDED.name,
          country = EXCLUDED.country,
          location = EXCLUDED.location,
          grand_prix = EXCLUDED.grand_prix,
          circuit = EXCLUDED.circuit,
          date = EXCLUDED.date
        RETURNING id
    """), {
        "name": name, "country": country, "location": location, "year": year,
        "round": round_no, "grand_prix": grand_prix or name, "circuit": circuit,
        "date": date_str
    }).mappings().first()
    return r["id"]

def upsert_result(conn, race_id, driver_id, grid, pos, status, time_ms, points):
    conn.execute(text("""
        INSERT INTO race_results (race_id, driver_id, grid, position, status, time_ms, points)
        VALUES (:race_id, :driver_id, :grid, :position, :status, :time_ms, :points)
        ON CONFLICT ON CONSTRAINT unique_race_driver DO UPDATE SET
          grid = EXCLUDED.grid,
          position = EXCLUDED.position,
          status = EXCLUDED.status,
          time_ms = EXCLUDED.time_ms,
          points = EXCLUDED.points
    """), {
        "race_id": race_id,
        "driver_id": driver_id,
        "grid": grid,
        "position": pos,
        "status": status,
        "time_ms": time_ms,
        "points": points
    })

def seed_season(year: int, through_round: int | None):
    # Pull schedule
    schedule = fastf1.get_event_schedule(year)
    # Keep only GP rounds up to requested round (or up to today if None)
    today = datetime.now(timezone.utc).date()
    events = []
    for _, ev in schedule.iterrows():
      rnd = ev.get("RoundNumber", ev.get("Round", None))
      if pd.isna(rnd):
          continue
      rnd = int(rnd)
      if rnd <= 0:
          # round 0 or negative = pre-season testing, skip it
          continue

      # Skip if it's explicitly a testing event
      name = str(ev.get("EventName") or ev.get("OfficialEventName") or "").lower()
      fmt  = str(ev.get("EventFormat") or "").lower()
      etyp = str(ev.get("EventType") or ev.get("Event") or "").lower()
      if "test" in name or "testing" in name or fmt == "testing" or etyp == "testing":
          continue

      date_val = ev.get("EventDate") or ev.get("Session1Date") or ev.get("StartDate")
      date = pd.to_datetime(date_val).date() if (date_val is not None and not pd.isna(date_val)) else None

      if through_round is not None and rnd > through_round:
          continue
      if through_round is None and (date is None or date > today):
          continue

      events.append((rnd, ev))

    events.sort(key=lambda x: x[0])

    with engine.begin() as conn:
        for rnd, ev in events:
            gp_name = str(ev.get("EventName") or ev.get("OfficialEventName") or "Grand Prix")
            country = ev.get("Country") if "Country" in ev else None
            location = ev.get("Location") if "Location" in ev else None
            circuit = ev.get("Circuit") if "Circuit" in ev else None
            date = ev.get("EventDate") or ev.get("Session3Date") or ev.get("Session2Date") or ev.get("Session1Date")
            date = pd.to_datetime(date).date() if not pd.isna(date) else None
            date_str = str(date) if date else None

            race_id = upsert_race(conn,
                                  year=year, round_no=rnd,
                                  name=gp_name, country=country, location=location,
                                  grand_prix=gp_name, circuit=circuit, date_str=date_str)

            # Load RACE session classification
            session = fastf1.get_session(year, rnd, "R")
            try:
                session.load()
            except Exception:
                print(f"Skipping {year} R{rnd} ({gp_name}) — no race classification yet.")
                continue

            if session.results is None or len(session.results) == 0:
                print(f"Skipping {year} R{rnd} ({gp_name}) — empty results.")
                continue

            results = session.results
            # Columns vary slightly by FastF1 version; handle defensively
            for row in results.itertuples():
                drv_code = getattr(row, "Abbreviation", None) or getattr(row, "Driver", None)
                drv_name = getattr(row, "FullName", None) or getattr(row, "Driver", None)
                team_name = getattr(row, "TeamName", None) or getattr(row, "Team", None)

                if not drv_code or not drv_name or not team_name:
                    # Skip weird rows
                    continue

                team_id = upsert_team(conn, team_name)
                driver_id = upsert_driver(conn, drv_code, drv_name, team_id)

                finish_pos = getattr(row, "Position", None)
                # Some versions have ClassifiedPosition; prefer numeric
                if pd.isna(finish_pos):
                    finish_pos = getattr(row, "ClassifiedPosition", None)
                finish_pos = int(finish_pos) if (finish_pos is not None and not pd.isna(finish_pos)) else None

                grid_pos = getattr(row, "GridPosition", None)
                grid_pos = int(grid_pos) if (grid_pos is not None and not pd.isna(grid_pos)) else None

                status = getattr(row, "Status", None)
                pts = getattr(row, "Points", None)
                pts = float(pts) if (pts is not None and not pd.isna(pts)) else None

                # Race time may be Timedelta or None
                rtime = getattr(row, "Time", None)
                time_ms = to_ms(rtime)

                upsert_result(conn, race_id, driver_id, grid_pos, finish_pos, status, time_ms, pts)

            print(f"Seeded {year} R{rnd}: {gp_name}")

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--season", type=int, default=2025, help="Season to seed, e.g., 2025")
    ap.add_argument("--through-round", type=int, default=None, help="Seed up to this round (inclusive). Default: through today")
    args = ap.parse_args()
    seed_season(args.season, args.through_round)
    print("Done.")
