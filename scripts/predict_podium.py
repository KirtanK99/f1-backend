# scripts/predict_podium.py
import os
import argparse
import joblib
import numpy as np
import pandas as pd
from sqlalchemy import create_engine, text
from sklearn.preprocessing import OneHotEncoder
from sklearn.compose import ColumnTransformer
from sqlalchemy import text


def ensure_race_and_stubs(engine, season: int, round_no: int):
    with engine.begin() as conn:
        # Upsert the race row if missing
        conn.execute(
            text(
                """
            INSERT INTO races (name, country, location, year, round, grand_prix, circuit, date)
            VALUES ('Round ' || :rnd, NULL, NULL, :yr, :rnd, 'Round ' || :rnd, NULL, NULL)
            ON CONFLICT ON CONSTRAINT unique_races_year_round DO NOTHING;
        """
            ),
            {"yr": season, "rnd": round_no},
        )

        # Create stub race_results for all drivers if missing
        conn.execute(
            text(
                """
            INSERT INTO race_results (race_id, driver_id, grid, position, status, time_ms, points)
            SELECT r.id, d.id, NULL, NULL, NULL, NULL, NULL
            FROM races r
            CROSS JOIN drivers d
            WHERE r.year = :yr AND r.round = :rnd
            ON CONFLICT ON CONSTRAINT unique_race_driver DO NOTHING;
        """
            ),
            {"yr": season, "rnd": round_no},
        )


DB_URL = os.getenv("DATABASE_URL")
MODEL_PATH = "models/podium_postqual_v1.joblib"


def add_rolling_features(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["is_podium"] = df["final_position"].isin([1, 2, 3]).astype(int)

    def roll_driver(g):
        g = g.sort_values(["season", "race_round"]).copy()
        g["driver_points_last_5"] = (
            g["race_points"].shift(1).rolling(5, min_periods=1).sum()
        )
        g["driver_podium_rate_last_5"] = (
            g["is_podium"].shift(1).rolling(5, min_periods=1).mean()
        )
        g["dnf_rate_last_5"] = (
            g["finish_status"]
            .shift(1)
            .isin(["DNF", "DSQ", "DNS", "DNQ"])
            .rolling(5, min_periods=1)
            .mean()
        )
        g["driver_grid_avg_last_3"] = (
            g["starting_position"].shift(1).rolling(3, min_periods=1).mean()
        )
        return g

    df = df.groupby("driver_id", group_keys=False).apply(
        roll_driver, include_groups=False
    )

    def roll_constructor(g):
        g = g.sort_values(["season", "race_round"]).copy()
        g["constructor_points_last_5"] = (
            g["race_points"].shift(1).rolling(5, min_periods=1).sum()
        )
        g["constructor_grid_avg_last_3"] = (
            g["starting_position"].shift(1).rolling(3, min_periods=1).mean()
        )
        return g

    df = df.groupby("constructor_id", group_keys=False).apply(
        roll_constructor, include_groups=False
    )

    df = df.sort_values(["constructor_id", "season", "race_round"]).copy()
    df["constructor_points_season_to_date"] = (
        df.groupby(["constructor_id", "season"])["race_points"]
        .apply(lambda s: s.shift(1).cumsum())
        .reset_index(level=[0, 1], drop=True)
    )

    # Fills
    fill_cols = [
        "driver_points_last_5",
        "driver_podium_rate_last_5",
        "dnf_rate_last_5",
        "driver_grid_avg_last_3",
        "constructor_points_last_5",
        "constructor_grid_avg_last_3",
        "constructor_points_season_to_date",
    ]
    for c in fill_cols:
        if df[c].isna().any():
            df[c] = df[c].fillna(df[c].median())

    if df["starting_position"].isna().any():
        if df["starting_position"].notna().any():
            df["starting_position"] = df["starting_position"].fillna(
                int(df["starting_position"].median())
            )
        else:
            df["starting_position"] = 20

    return df


def fetch_all_up_to(engine, season):
    sql = """
    SELECT
      r.id AS race_id,
      r.year AS season,
      r.round AS race_round,
      r.name AS race_name,
      r.grand_prix AS grand_prix,
      d.id AS driver_id,
      d.name AS driver_name,
      d.code AS driver_code,
      t.id AS constructor_id,
      t.name AS team_name,
      COALESCE(rr.grid, 20) AS starting_position,
      rr.position AS final_position,
      rr.status   AS finish_status,
      COALESCE(rr.points, 0.0) AS race_points
    FROM races r
    JOIN race_results rr ON rr.race_id = r.id
    JOIN drivers d       ON d.id = rr.driver_id
    JOIN teams   t       ON t.id = d.team_id
    WHERE r.year <= :season
    ORDER BY season, race_round, driver_id;
    """
    return pd.read_sql(text(sql), engine, params={"season": season})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--season", type=int, required=True, help="e.g., 2025")
    ap.add_argument("--round", type=int, required=True, help="e.g., 1")
    args = ap.parse_args()

    if not os.path.exists(MODEL_PATH):
        raise SystemExit(f"Model not found at {MODEL_PATH}. Train first.")

    engine = create_engine(DB_URL)
    df = fetch_all_up_to(engine, args.season)
    if df.empty:
        raise SystemExit("No data found. Seed races/race_results first.")

    df = add_rolling_features(df)
    # make sure the race + stubs exist
    ensure_race_and_stubs(engine, args.season, args.round)

    # re-fetch after ensuring stubs, so df includes them
    df = fetch_all_up_to(engine, args.season)
    df = add_rolling_features(df)
    cur = df[(df["season"] == args.season) & (df["race_round"] == args.round)].copy()

    # Header: race title
    title = None
    if "grand_prix" in cur and cur["grand_prix"].notna().any():
        title = cur["grand_prix"].dropna().iloc[0]
    elif "race_name" in cur and cur["race_name"].notna().any():
        title = cur["race_name"].dropna().iloc[0]
    else:
        title = f"Round {args.round}"

    print(f"\n=== {args.season} • Round {args.round} — {title} ===\n")
    if cur.empty:
        raise SystemExit("Target race not found. Create the race + race_results rows.")

    features_num = [
        "starting_position",
        "driver_points_last_5",
        "driver_podium_rate_last_5",
        "dnf_rate_last_5",
        "driver_grid_avg_last_3",
        "constructor_points_last_5",
        "constructor_grid_avg_last_3",
        "constructor_points_season_to_date",
        "race_round",
        "season",
    ]
    features_cat = ["constructor_id", "driver_id"]

    X = cur[features_num + features_cat]
    model = joblib.load(MODEL_PATH)
    cur["podium_prob"] = model.predict_proba(X)[:, 1]

    # Pretty print top 10
    out = (
        cur.sort_values("podium_prob", ascending=False)[
            ["driver_name", "team_name", "starting_position", "podium_prob"]
        ]
        .head(10)
        .reset_index(drop=True)
    )

    for i, row in out.iterrows():
        grid_val = (
            int(row.starting_position) if pd.notna(row.starting_position) else None
        )
        grid_str = f"{grid_val:>2}" if grid_val is not None else "--"
        print(
            f"{i+1:2d}. {row.driver_name:20s}  | {row.team_name:18s}  | grid={grid_str}  | prob={row.podium_prob:.3f}"
        )


if __name__ == "__main__":
    main()
