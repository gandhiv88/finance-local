from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    DATABASE_URL: str
    UPLOAD_DIR: str = "/data/uploads"
    ARCHIVE_DIR: str = "/data/archive"
    DEBUG_DIR: str = "/data/debug"
    OFFLINE_MODE: bool = True

settings = Settings()
