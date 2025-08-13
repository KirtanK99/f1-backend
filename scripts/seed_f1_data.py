import os
from typing import Optional, Set

import fastf1
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models.f1 import Race, Driver, Team, RaceResult  # RaceResult must exist

# -----------------------
# Strict env-based config
# -----------------------
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is not set.")

SEASON_STR = os.getenv("SEASON")
if not SEASON_STR:
    raise RuntimeError("SEASON is not set.")
try:
    SEASON = int(SEASON_STR)
except ValueError:
    raise RuntimeError(f"SEASON must be an integer, got: {SEASON_STR!r}")

FASTF1_CACHE_DIR = os.getenv("FASTF1_CACHE_DIR")
if FASTF1_CACHE_DIR:
    fastf1.Cache.enable_cache(FASTF1_CACHE_DIR)

STRICT_VERIFY = os.getenv("STRICT_VERIFY", "0") in {"1", "true", "True"}

# -----------------------
# DB session
# -----------------------
engine = create_engine(DATABASE_URL, future=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
session = SessionLocal()

# -----------------------
# Helpers
# -----------------------
def getv(row, *candidates, default=None):
    """Return the first present & non-None value from candidate column names in a pandas Series."""
    for c in candidates:
        if c in row and row[c] is not None:
            return row[c]
    return default

def is_nullish(val) -> bool:
    """True for None, NaN, or pandas NaT."""
    if val is None:
        return True
    try:
        return val != val  # NaN != NaN is True
    except Exception:
        return False

def to_opt_int(val):
    """Int or None, tolerant of NaN/None/strings."""
    if is_nullish(val):
        return None
    try:
        return int(val)
    except Exception:
        return None

def to_opt_float(val):
    """Float or None, tolerant of NaN/None/strings."""
    if is_nullish(val):
        return None
    try:
        f = float(val)
        return None if f != f else f  # handle NaN
    except Exception:
        return None

def to_ms(val):
    """Convert pandas Timedelta/np.timedelta64/number to milliseconds; None for NaN/NaT."""
    if is_nullish(val):
        return None
    # pandas.Timedelta
    try:
        import pandas as pd
        if isinstance(val, pd.Timedelta):
            return int(val.total_seconds() * 1000)
    except Exception:
        pass
    # numpy.timedelta64
    try:
        import numpy as np, pandas as pd
        if isinstance(val, np.timedelta64):
            return int(pd.to_timedelta(val).total_seconds() * 1000)
    except Exception:
        pass
    # already numeric
    return to_opt_int(val)


def get_or_create_team(name: str) -> Team:
    team = session.query(Team).filter_by(name=name).first()
    if team:
        return team
    team = Team(name=name)
    session.add(team)
    session.flush()  # ensure team.id is available
    return team

def get_or_create_driver(code: str, full_name: str, team_id: int, nationality: Optional[str] = None) -> Driver:
    drv = session.query(Driver).filter_by(code=code).first()
    if drv:
        changed = False
        if drv.team_id is None and team_id is not None:
            drv.team_id = team_id; changed = True
        if nationality and not getattr(drv, "nationality", None):
            drv.nationality = nationality; changed = True
        if changed:
            session.add(drv)
        return drv
    drv = Driver(code=code, name=full_name, team_id=team_id, nationality=nationality)
    session.add(drv)
    session.flush()
    return drv

def get_or_create_race(event_row, season: int) -> Race:
    """Create/fetch a Race using (season, RoundNumber)."""
    year = int(season)
    rnd = getv(event_row, "RoundNumber")
    if rnd is None:
        raise ValueError("Schedule row is missing 'RoundNumber'; cannot create Race.")
    rnd = int(rnd)

    race = session.query(Race).filter_by(year=year, round=rnd).first()
    if race:
        return race

    name = getv(event_row, "EventName", "OfficialEventName", default="Unknown GP")
    country = getv(event_row, "Country", "EventCountry")
    location = getv(event_row, "Location", "EventLocation")
    circuit = getv(event_row, "CircuitShortName", "CircuitName")
    date_val = getv(event_row, "EventDate")
    if hasattr(date_val, "date"):
        date_val = date_val.date()

    race = Race(
        name=name,
        country=country,
        location=location,
        year=year,
        round=rnd,
        grand_prix=name,
        circuit=circuit,
        date=date_val,
    )
    session.add(race)
    session.flush()
    return race

def upsert_race_result(*, race_id: int, driver_id: int,
                       position: Optional[int], grid: Optional[int],
                       status: Optional[str], time_ms: Optional[int],
                       points: Optional[float]):
    """Insert/update one race result row per (race_id, driver_id)."""
    rr = session.query(RaceResult).filter_by(race_id=race_id, driver_id=driver_id).first()
    if rr:
        rr.position = position if position is not None else rr.position
        rr.grid     = grid     if grid     is not None else rr.grid
        rr.status   = status   if status   is not None else rr.status
        rr.time_ms  = time_ms  if time_ms  is not None else rr.time_ms
        rr.points   = points   if points   is not None else rr.points
        session.add(rr)
        return rr

    rr = RaceResult(
        race_id=race_id,
        driver_id=driver_id,
        position=position,
        grid=grid,
        status=status,
        time_ms=time_ms,
        points=points,
    )
    session.add(rr)
    return rr

# -----------------------
# Main
# -----------------------
def seed_season(season: int):
    schedule = fastf1.get_event_schedule(season)
    print("Schedule columns:", list(schedule.columns))
    total_inserted_or_updated = 0
    rounds_with_issues = []

    for _, event in schedule.iterrows():
        race = get_or_create_race(event, season)
        session.flush()

        # Load final race classification
        event_name = getv(event, "EventName", "OfficialEventName", default="(unknown)")
        try:
            round_num = int(getv(event, "RoundNumber", default=0))
            sess = fastf1.get_session(season, round_num, "R")
            sess.load()
        except Exception as e:
            print(f"⚠️  Round {round_num:>2} {event_name}: skipping (no session or not loaded) → {e}")
            rounds_with_issues.append((round_num, event_name, "session_load_failed"))
            continue

        if getattr(sess, "results", None) is None:
            print(f"⚠️  Round {round_num:>2} {event_name}: no results dataframe")
            rounds_with_issues.append((round_num, event_name, "no_results_df"))
            continue

        # Track what we expect to store for this round
        expected_abbrs: Set[str] = set()
        skipped_incomplete = 0
        before_count = session.query(RaceResult).filter_by(race_id=race.id).count()

        for _, row in sess.results.iterrows():
            team_name  = row.get("TeamName")
            abbr       = row.get("Abbreviation")
            first      = row.get("FirstName") or ""
            last       = row.get("LastName") or ""
            full_name  = f"{first} {last}".strip()

            if not team_name or not abbr or not full_name:
                skipped_incomplete += 1
                continue

            expected_abbrs.add(abbr)

            team = get_or_create_team(team_name)
            driver = get_or_create_driver(code=abbr, full_name=full_name, team_id=team.id)

            # ---- CHANGED: null-safe extraction + fallbacks ----
            position = to_opt_int(row.get("Position"))
            grid     = to_opt_int(row.get("GridPosition") or row.get("Grid"))
            status   = row.get("Status")
            time_ms  = to_ms(row.get("Time"))
            points   = to_opt_float(row.get("Points"))

            upsert_race_result(
                race_id=race.id,
                driver_id=driver.id,
                position=position,
                grid=grid,
                status=status,
                time_ms=time_ms,
                points=points,
            )

        # ---- CHANGED: flush so verification queries see inserted rows ----
        session.flush()

        after_count = session.query(RaceResult).filter_by(race_id=race.id).count()
        # Which driver codes actually landed in DB for this race?
        db_abbrs = {
            code for (code,) in session.query(Driver.code)
            .join(RaceResult, RaceResult.driver_id == Driver.id)
            .filter(RaceResult.race_id == race.id)
            .all()
        }

        missing = expected_abbrs - db_abbrs
        inserted_or_updated = max(0, after_count - before_count)
        total_inserted_or_updated += inserted_or_updated

        if missing:
            print(
                f"❗ Round {round_num:>2} {event_name}: expected {len(expected_abbrs)} results, "
                f"found {len(db_abbrs)}. Missing: {sorted(missing)} "
                f"(skipped incomplete rows: {skipped_incomplete})"
            )
            rounds_with_issues.append((round_num, event_name, f"missing:{sorted(missing)}"))
            if STRICT_VERIFY:
                session.rollback()
                raise RuntimeError(f"Strict verify failed for round {round_num}: {sorted(missing)}")
        else:
            print(
                f"✅ Round {round_num:>2} {event_name}: stored {len(db_abbrs)} results "
                f"(+{inserted_or_updated} new/updated, skipped incomplete: {skipped_incomplete})"
            )

    session.commit()
    print(f"\n✅ Seed complete for {season}! New/updated results this run: +{total_inserted_or_updated}")
    if rounds_with_issues:
        print("⚠️ Rounds with issues:")
        for r in rounds_with_issues:
            print("   -", r)

if __name__ == "__main__":
    seed_season(SEASON)
