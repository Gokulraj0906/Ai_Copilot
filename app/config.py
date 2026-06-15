from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    openrouter_api_key: str
    database_url: str = "postgresql+asyncpg://copilot:copilot@localhost:5432/copilot"
    redis_url: str

    class Config:
        env_file = ".env"


settings = Settings()