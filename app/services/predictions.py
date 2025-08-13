from typing import List, Dict
import math

# Dummy model: softmax on starting positions (inverse rank). Replace with real model later.
def predict_win_probs(grid: List[Dict]) -> List[Dict]:
    # Lower position number => higher base score
    scores = []
    for row in grid:
        # Simple heuristic: score = 1 / position
        pos = row["position"]
        scores.append(1.0 / pos)

    # softmax normalization
    exp_scores = [math.exp(s) for s in scores]
    denom = sum(exp_scores) or 1.0
    probs = [e / denom for e in exp_scores]

    out = []
    for row, p in zip(grid, probs):
        out.append({
            "driver_id": row["driver_id"],
            "driver_code": row["driver_code"],
            "p_win": round(p, 4),
            "p_podium": round(min(1.0, p * 2.5), 4),  # placeholder
        })
    return out
