from fastapi import APIRouter, HTTPException
from typing import List
from app.schemas.races import Prediction
from app.services import races as race_service
from app.services import predictions as pred_service

router = APIRouter()

@router.get("/races/{race_id}/prediction", response_model=List[Prediction])
def race_prediction(race_id: int):
    grid = race_service.get_grid_for_race(race_id)
    if not grid:
        raise HTTPException(404, "No grid available for prediction")
    return pred_service.predict_win_probs(grid)
