import os

class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "chai-pe-charcha-flask-secret-key-2025-secure")
    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL", "sqlite:///chai_pe_charcha.db")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    JWT_SECRET_KEY = os.environ.get("JWT_SECRET_KEY", "chai-pe-charcha-jwt-secret-key-2025-secure")
    JWT_ACCESS_TOKEN_EXPIRES = 86400   # 24 hours
