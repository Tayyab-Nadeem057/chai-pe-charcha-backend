import os

class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "chai-pe-charcha-secret-2025")
    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL", "sqlite:///chai_pe_charcha.db")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    JWT_SECRET_KEY = os.environ.get("JWT_SECRET_KEY", "jwt-chai-secret-2025")
    JWT_ACCESS_TOKEN_EXPIRES = 86400   # 24 hours
