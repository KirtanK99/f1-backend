from fastapi import APIRouter, Depends, HTTPException, Query
from fastf1.ergast import Ergast
from sqlalchemy.orm import Session
from sqlalchemy import text
from app.db.session import get_db
from app.schemas.stats import WinsRacesResponse, DriversLeaderboardResponse, DriverRow, RaceWin


router = APIRouter()

def _ensure_driver(db: Session, code: str):
    exists = db.execute(
        text("SELECT 1 FROM drivers WHERE code = :code LIMIT 1"),
        {"code": code}
    ).first()
    if not exists:
        raise HTTPException(404, detail=f"Driver code '{code}' not found")

@router.get("/wins")
def wins(driver: str = Query(..., description="Driver code, e.g., VER"),
         season: int = Query(2024, ge=1950),
         db: Session = Depends(get_db)):
    code = driver.upper()
    _ensure_driver(db, code)
    row = db.execute(text("""
        SELECT COUNT(*) AS wins
        FROM race_results rr
        JOIN races r   ON r.id = rr.race_id
        JOIN drivers d ON d.id = rr.driver_id
        WHERE d.code = :code AND r.year = :season AND rr.position = 1
    """), {"code": code, "season": season}).one()
    return {"driver": code, "season": season, "wins": int(row.wins)}

@router.get("/wins/races", response_model=WinsRacesResponse)
def wins_races(
    driver: str = Query(..., description="Driver code, e.g., VER, LEC, NOR"),
    season: int = Query(2024, ge=1950, description="Season year"),
    db: Session = Depends(get_db),
):
    code = driver.upper()

    # Ensure the driver exists
    exists = db.execute(text("SELECT 1 FROM drivers WHERE code = :code LIMIT 1"),
                        {"code": code}).first()
    if not exists:
        raise HTTPException(status_code=404, detail=f"Driver code '{code}' not found")

    rows = db.execute(
      text("""
            SELECT
                r.id        AS race_id,
                r.round     AS round,
                to_char(r.date, 'YYYY-MM-DD') AS date,  -- cast to string
                COALESCE(r.grand_prix, r.name) AS grand_prix,
                r.country,
                r.location,
                r.circuit
            FROM race_results rr
            JOIN races r   ON r.id = rr.race_id
            JOIN drivers d ON d.id = rr.driver_id
            WHERE d.code = :code
              AND r.year = :season
              AND rr.position = 1
            ORDER BY r.round ASC, r.date ASC
          """),
      {"code": code, "season": season},
    ).mappings().all()

    return {
        "driver": code,
        "season": season,
        "wins_count": len(rows),
        "races": [
            {
                "race_id": r["race_id"],
                "round": r["round"],
                "date": r["date"],
                "grand_prix": r["grand_prix"],
                "country": r["country"],
                "location": r["location"],
                "circuit": r["circuit"],
            } for r in rows
        ],
    }



@router.get("/podiums")
def podiums(driver: str = Query(...), season: int = Query(2024, ge=1950),
            db: Session = Depends(get_db)):
    code = driver.upper()
    _ensure_driver(db, code)
    row = db.execute(text("""
        SELECT COUNT(*) AS podiums
        FROM race_results rr
        JOIN races r   ON r.id = rr.race_id
        JOIN drivers d ON d.id = rr.driver_id
        WHERE d.code = :code AND r.year = :season AND rr.position IN (1,2,3)
    """), {"code": code, "season": season}).one()
    return {"driver": code, "season": season, "podiums": int(row.podiums)}

@router.get("/points")
def points(driver: str = Query(...), season: int = Query(2024, ge=1950),
           db: Session = Depends(get_db)):
    code = driver.upper()
    _ensure_driver(db, code)
    row = db.execute(text("""
        SELECT COALESCE(SUM(rr.points), 0) AS points
        FROM race_results rr
        JOIN races r   ON r.id = rr.race_id
        JOIN drivers d ON d.id = rr.driver_id
        WHERE d.code = :code AND r.year = :season
    """), {"code": code, "season": season}).one()
    return {"driver": code, "season": season, "points": float(row.points or 0)}

@router.get("/summary")
def summary(driver: str = Query(...), season: int = Query(2024, ge=1950),
            db: Session = Depends(get_db)):
    code = driver.upper()
    _ensure_driver(db, code)
    rows = db.execute(text("""
        WITH wins AS (
          SELECT COUNT(*) AS c FROM race_results rr
          JOIN races r ON r.id = rr.race_id
          JOIN drivers d ON d.id = rr.driver_id
          WHERE d.code = :code AND r.year = :season AND rr.position = 1
        ),
        podiums AS (
          SELECT COUNT(*) AS c FROM race_results rr
          JOIN races r ON r.id = rr.race_id
          JOIN drivers d ON d.id = rr.driver_id
          WHERE d.code = :code AND r.year = :season AND rr.position IN (1,2,3)
        ),
        points AS (
          SELECT COALESCE(SUM(rr.points),0) AS s FROM race_results rr
          JOIN races r ON r.id = rr.race_id
          JOIN drivers d ON d.id = rr.driver_id
          WHERE d.code = :code AND r.year = :season
        )
        SELECT wins.c AS wins, podiums.c AS podiums, points.s AS points
        FROM wins, podiums, points
    """), {"code": code, "season": season}).one()
    return {
        "driver": code,
        "season": season,
        "wins": int(rows.wins or 0),
        "podiums": int(rows.podiums or 0),
        "points": float(rows.points or 0.0),
    }

@router.get("/leaderboard", response_model=DriversLeaderboardResponse)
def drivers_leaderboard(
    season: int = Query(2024, ge=1950, description="Season year"),
    limit: int = Query(20, ge=1, le=100, description="Max number of drivers"),
    db: Session = Depends(get_db),
):
    """
    Driver standings for a season, ordered by total points (then wins).
    """
    rows = db.execute(
        text("""
            SELECT
                d.code        AS code,
                d.name        AS driver_name,
                COALESCE(t.name, '') AS team_name,
                COALESCE(SUM(rr.points), 0) AS points,
                SUM(CASE WHEN rr.position = 1 THEN 1 ELSE 0 END) AS wins,
                SUM(CASE WHEN rr.position IN (1,2,3) THEN 1 ELSE 0 END) AS podiums
            FROM race_results rr
            JOIN races   r ON r.id = rr.race_id
            JOIN drivers d ON d.id = rr.driver_id
            LEFT JOIN teams t ON t.id = d.team_id
            WHERE r.year = :season
            GROUP BY d.code, d.name, t.name
            ORDER BY points DESC, wins DESC, d.code ASC
            LIMIT :limit
        """),
        {"season": season, "limit": limit},
    ).mappings().all()

    return {
        "season": season,
        "count": len(rows),
        "drivers": [
            {
                "code": r["code"],
                "name": r["driver_name"],
                "team": r["team_name"] or None,
                "points": float(r["points"] or 0),
                "wins": int(r["wins"] or 0),
                "podiums": int(r["podiums"] or 0),
            } for r in rows
        ],
    }

@router.get("/constructors", response_model=ConstructorsLeaderboardResponse)
def constructors_leaderboard(
    season: int = Query(2024, ge=1950),
    limit: int = Query(10, ge=1, le=100),
    db: Session = Depends(get_db),
):
    rows = db.execute(text("""
          SELECT
            COALESCE(t.name, 'Unknown') AS team,
            COALESCE(SUM(rr.points), 0) AS points,
            SUM(CASE WHEN rr.position = 1 THEN 1 ELSE 0 END) AS wins,
            SUM(CASE WHEN rr.position IN (1,2,3) THEN 1 ELSE 0 END) AS podiums
          FROM race_results rr
          JOIN races   r ON r.id = rr.race_id
          JOIN drivers d ON d.id = rr.driver_id
          LEFT JOIN teams   t ON t.id = d.team_id
          WHERE r.year = :season
          GROUP BY COALESCE(t.name, 'Unknown')
          ORDER BY points DESC, wins DESC, podiums DESC, team ASC
          LIMIT :limit
      """), {"season": season, "limit": limit}).mappings().all()
    return {"season": season, "count": len(rows), "constructors": [
        {"team": r["team"], "points": float(r["points"] or 0),
         "wins": int(r["wins"] or 0), "podiums": int(r["podiums"] or 0)}
        for r in rows
    ]}
