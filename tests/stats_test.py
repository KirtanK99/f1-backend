from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"

def test_wins_races_shape():
    r = client.get("/stats/wins/races?driver=VER&season=2024")
    assert r.status_code == 200
    body = r.json()
    for k in ["driver", "season", "wins_count", "races"]:
        assert k in body
    if body["races"]:
        first = body["races"][0]
        # required fields present
        for k in ["race_id", "round", "date", "grand_prix"]:
            assert k in first
        # types sanity
        assert isinstance(first["race_id"], int)
        assert isinstance(first["round"], int)
        assert isinstance(first["date"], str)
        assert isinstance(first["grand_prix"], str)

def test_leaderboard_ok():
    r = client.get("/stats/leaderboard?season=2024&limit=5")
    assert r.status_code == 200
    body = r.json()
    assert body["season"] == 2024
    assert "drivers" in body
