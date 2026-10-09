import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    # Database configuration
    DB_HOST = os.getenv("DB_HOST", "192.168.100.250")
    DB_PORT = int(os.getenv("DB_PORT", "3306"))
    DB_NAME = os.getenv("DB_NAME", "djo1707")
    DB_USER = os.getenv("DB_USER", "diva")
    DB_PASSWORD = os.getenv("DB_PASSWORD", "diva")
    DB_CHARSET = os.getenv("DB_CHARSET", "utf8mb4")

    # App configuration
    PAGE_TITLE = "Djo"
    PAGE_ICON = "🏭"


config = Config()