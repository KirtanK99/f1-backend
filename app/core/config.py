from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    env: str
    database_url: str
    ergast_url: str
    season: str
    fastf1_cache_dir: str | None = None
    pythonunbuffered: int | None = None

    class Config:
        env_file = ".env"
        env_prefix = ""
        case_sensitive = False

settings = Settings()
