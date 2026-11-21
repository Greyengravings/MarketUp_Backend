from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "MarketUp API"
    database_url: str = "sqlite:///./marketup.db"

    # JWT
    jwt_secret_key: str = "CHANGE_ME_IN_PRODUCTION"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 30

    # AI
    api_key: str = ""
    gemini_model: str = "gemini-2.5-flash"
    gemini_image_model: str = "gemini-nano-banana-2.1"

    class Config:
        env_file = ".env"


settings = Settings()
