import os

class Config:
    MONGO_URI = os.getenv("MONGO_URI")
    SITE_BASE_URL = os.getenv("SITE_BASE_URL", "https://todaysus.com").rstrip("/")
