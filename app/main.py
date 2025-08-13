from fastapi import FastAPI
from app.api.routes import health, races, predictions

app = FastAPI(title="F1 Analytics API", version="0.1.0")

# Routers
app.include_router(health.router, tags=["system"])
app.include_router(races.router, prefix="/races", tags=["races"])
app.include_router(predictions.router, tags=["predictions"])

@app.get("/", include_in_schema=False)
def root():
    return {"message": "F1 Analytics API - see /docs"}
