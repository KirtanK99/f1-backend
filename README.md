# F1 Backend (FastAPI + Postgres + SQLAlchemy + Alembic + FastF1)

Production-style backend that ingests Formula 1 data via FastF1 and stores it in Postgres.
Includes idempotent seeding, migration-managed schema, and verification checks.

## Tech
- FastAPI, Uvicorn
- SQLAlchemy ORM, Alembic
- Postgres 16 (Docker)
- FastF1, Pandas, NumPy
- Pydantic Settings
- Docker Compose

## Quickstart
```bash
cp .env.example .env             # fill in values as needed
docker compose up -d             # api + db
docker compose exec api bash -lc 'alembic upgrade head'
docker compose exec \
  -e SEASON=2024 \
  api bash -lc 'python -m scripts.seed_f1_data'
