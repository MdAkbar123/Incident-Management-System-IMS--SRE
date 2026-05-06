from pydantic_settings import BaseSettings
#This code is using Pydantic, a library used for data validation and settings management. It’s a clean way to handle configuration (like database credentials) in a Python application.
#config.py file acts as the central nervous system for your application's environment configuration.
class Settings(BaseSettings):
    # MySQL
    mysql_host: str = "localhost"
    mysql_port: int = 3306
    mysql_user: str = "ims_user"
    mysql_password: str = "ims_pass"
    mysql_db: str = "ims_db"

    # MongoDB
    mongo_uri: str = "mongodb://localhost:27017"
    mongo_db: str = "ims_db"

    # Redis
    redis_host: str = "localhost"
    redis_port: int = 6379

    # InfluxDB
    influx_url: str = "http://localhost:8086"
    influx_token: str = "ims-super-secret-token"
    influx_org: str = "ims_org"
    influx_bucket: str = "ims_bucket"

    @property
    def mysql_url_async(self) -> str:
        return (
            f"mysql+asyncmy://{self.mysql_user}:{self.mysql_password}"
            f"@{self.mysql_host}:{self.mysql_port}/{self.mysql_db}"
        )

    @property
    def mysql_url_sync(self) -> str:
        # Alembic needs a sync URL for migrations
        return (
            f"mysql+pymysql://{self.mysql_user}:{self.mysql_password}"
            f"@{self.mysql_host}:{self.mysql_port}/{self.mysql_db}"
        )

    class Config:
        env_file = ".env"

settings = Settings()
