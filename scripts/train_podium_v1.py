import os
import joblib
import numpy as np
import pandas as pd
from pathlib import Path
from sqlalchemy import create_engine, text
from sklearn.model_selection import GroupKFold
from sklearn.metrics import roc_auc_score, average_precision_score
from sklearn.preprocessing import OneHotEncoder
from sklearn.compose import ColumnTransformer
from sklearn.pipeline import Pipeline
from sklearn.ensemble import GradientBoostingClassifier

# Use env var
DB_URL = os.getenv("DATABASE_URL")
MODEL_DIR = Path("./models")
MODEL_DIR.mkdir(parents=True, exist_ok=True)
MODEL_PATH = MODEL_DIR / "podium_postqual_v1.joblib"

def fetch_base(engine):
    sql = """
    WITH base AS (
      SELECT
        r.id   AS race_id,
        r.year AS season,
        r.round AS race_round,
        d.id   AS driver_id,
        t.id   AS constructor_id,
        COALESCE(rr.grid, 20)     AS starting_position,  -- from race_results.grid
        rr.position               AS final_position,     -- can be NULL for DNF/DSQ
        rr.status                 AS finish_status,
        COALESCE(rr.points, 0.0)  AS race_points
      FROM races r
      JOIN race_results rr ON rr.race_id = r.id
      JOIN drivers d       ON d.id = rr.driver_id
      JOIN teams t         ON t.id = d.team_id
    )
    SELECT * FROM base
    ORDER BY season, race_round, driver_id;
    """
    return pd.read_sql(text(sql), engine)

def add_rolling_features(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    # Target: podium (1..3)
    df["is_podium"] = df["final_position"].isin([1, 2, 3]).astype(int)

    # Driver rolling (exclude current race with shift(1))
    def roll_driver(g):
        g = g.sort_values(["season", "race_round"]).copy()
        g["driver_points_last_5"] = g["race_points"].shift(1).rolling(5, min_periods=1).sum()
        g["driver_podium_rate_last_5"] = g["is_podium"].shift(1).rolling(5, min_periods=1).mean()
        g["dnf_rate_last_5"] = g["finish_status"].shift(1).isin(["DNF", "DSQ", "DNS", "DNQ"]).rolling(5, min_periods=1).mean()
        g["driver_grid_avg_last_3"] = g["starting_position"].shift(1).rolling(3, min_periods=1).mean()
        return g

    df = df.groupby("driver_id", group_keys=False).apply(roll_driver)

    # Constructor rolling
    def roll_constructor(g):
        g = g.sort_values(["season", "race_round"]).copy()
        g["constructor_points_last_5"] = g["race_points"].shift(1).rolling(5, min_periods=1).sum()
        g["constructor_grid_avg_last_3"] = g["starting_position"].shift(1).rolling(3, min_periods=1).mean()
        return g

    df = df.groupby("constructor_id", group_keys=False).apply(roll_constructor)

    # Season-to-date constructor points up to previous round
    df = df.sort_values(["constructor_id", "season", "race_round"]).copy()
    df["constructor_points_season_to_date"] = (
        df.groupby(["constructor_id", "season"])["race_points"]
          .apply(lambda s: s.shift(1).cumsum())
          .reset_index(level=[0,1], drop=True)
    )

    # Fill NaNs from early rounds
    fill_cols = [
        "driver_points_last_5","driver_podium_rate_last_5","dnf_rate_last_5",
        "driver_grid_avg_last_3","constructor_points_last_5","constructor_grid_avg_last_3",
        "constructor_points_season_to_date"
    ]
    for c in fill_cols:
        if df[c].isna().any():
            df[c] = df[c].fillna(df[c].median())

    # Ensure starting_position has no NaNs
    if df["starting_position"].isna().any():
        if df["starting_position"].notna().any():
            df["starting_position"] = df["starting_position"].fillna(int(df["starting_position"].median()))
        else:
            df["starting_position"] = 20  # worst-case fallback

    return df

def build_dataset(engine):
    df = fetch_base(engine)
    if df.empty:
        raise RuntimeError("No data returned from DB. Ensure races and race_results are populated.")

    df = add_rolling_features(df)

    # Drop rows with unknown final position from training
    train_df = df.dropna(subset=["final_position"]).copy()
    if train_df.empty:
        raise RuntimeError("Training set is empty (no rows with final_position).")

    features_num = [
        "starting_position",
        "driver_points_last_5","driver_podium_rate_last_5","dnf_rate_last_5",
        "driver_grid_avg_last_3",
        "constructor_points_last_5","constructor_grid_avg_last_3",
        "constructor_points_season_to_date",
        "race_round","season"
    ]
    features_cat = ["constructor_id","driver_id"]

    X = train_df[features_num + features_cat]
    y = train_df["is_podium"].astype(int)
    groups = train_df["race_id"]

    pre = ColumnTransformer(
        transformers=[
            ("num", "passthrough", features_num),
            ("cat", OneHotEncoder(handle_unknown="ignore", sparse_output=True), features_cat),
        ]
    )

    model = GradientBoostingClassifier(random_state=42)
    clf = Pipeline(steps=[("pre", pre), ("clf", model)])
    return clf, X, y, groups

def cv_evaluate(clf, X, y, groups):
    # Make sure we have enough races for CV
    n_groups = int(groups.nunique())
    n_splits = max(2, min(5, n_groups))  # 2..5
    if n_groups < 2:
        return None  # not enough races for CV

    gkf = GroupKFold(n_splits=n_splits)
    aucs, aps = [], []
    for tr, va in gkf.split(X, y, groups):
        clf.fit(X.iloc[tr], y.iloc[tr])
        p = clf.predict_proba(X.iloc[va])[:, 1]
        aucs.append(roc_auc_score(y.iloc[va], p))
        aps.append(average_precision_score(y.iloc[va], p))
    return np.mean(aucs), np.std(aucs), np.mean(aps), np.std(aps)

def train_and_save():
    engine = create_engine(DB_URL)

    clf, X, y, groups = build_dataset(engine)

    cv_stats = cv_evaluate(clf, X, y, groups)
    if cv_stats is not None:
        mean_auc, std_auc, mean_ap, std_ap = cv_stats
        print(f"[CV] ROC-AUC: {mean_auc:.3f} ± {std_auc:.3f} | AP: {mean_ap:.3f} ± {std_ap:.3f}")
    else:
        print("[CV] Skipped (not enough distinct races for cross-validation)")

    # Train on full data and save
    clf.fit(X, y)
    joblib.dump(clf, MODEL_PATH)
    print(f"Saved model -> {MODEL_PATH}")

if __name__ == "__main__":
    train_and_save()
