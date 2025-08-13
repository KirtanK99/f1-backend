.PHONY: up down logs migrate seed backfill test fmt lint dbsh health

up:        ## Start services
	docker compose up -d

down:      ## Stop services
	docker compose down

logs:      ## Tail API logs
	docker compose logs -f api

migrate:   ## Apply alembic migrations
	docker compose exec api alembic upgrade head

seed:      ## Seed season data
	docker compose exec api python -c "from app.seed import seed_season; seed_season(2024)"

backfill:  ## Backfill circuit names via Ergast/Jolpi
	docker compose exec api python -c "from app.services.datafix import backfill_circuit_names as f; print(f(2024))"

test:      ## Run pytest in the api container
	docker compose exec api python -m pytest -q

fmt:       ## Format with ruff
	docker compose exec api ruff format .

lint:      ## Lint with ruff
	docker compose exec api ruff check .

dbsh:      ## Open psql shell
	docker compose exec db psql -U f1 -d f1

health:    ## Hit /health
	curl -sS http://localhost:8000/health | jq .

# --- Quality-of-life targets ---

restart:        ## Restart all services (api + db)
	docker compose restart

restart-api:    ## Restart only the API
	docker compose restart api

rebuild:        ## Rebuild API image with no cache and start it
	docker compose build --no-cache api
	docker compose up -d api

ps:             ## List running services
	docker compose ps

api-sh:         ## Shell into the API container
	docker compose exec api sh

db-logs:        ## Tail DB logs
	docker compose logs -f db

downv:          ## Stop & remove containers + volumes (DESTROYS DATA) — use: make downv CONFIRM=1
	@test "$(CONFIRM)" = "1" || (echo "Refusing: set CONFIRM=1 to run 'make downv'"; exit 1)
	docker compose down -v

help:           ## Show this help
	@grep -E '^[a-zA-Z0-9_.-]+:.*?## ' Makefile | sed 's/:.*##/: /' | sort

