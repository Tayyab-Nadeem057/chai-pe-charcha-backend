import os
import tempfile

# Secrets must exist before config.py is imported.
os.environ.setdefault("SECRET_KEY", "test-secret-key")
os.environ.setdefault("JWT_SECRET_KEY", "test-jwt-key")

import pytest
from werkzeug.security import generate_password_hash
from flask_jwt_extended import create_access_token

from config import Config
from app import create_app, db
from app.models import User

_db_fd, _db_path = tempfile.mkstemp(suffix=".db")


class TestConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = f"sqlite:///{_db_path}"
    # Allow header tokens in tests (production uses cookies) and skip CSRF/rate limits.
    JWT_TOKEN_LOCATION = ["headers", "cookies"]
    JWT_COOKIE_CSRF_PROTECT = False
    JWT_COOKIE_SECURE = False
    RATELIMIT_ENABLED = False


@pytest.fixture(scope="session")
def app():
    application = create_app(TestConfig)
    yield application
    os.close(_db_fd)
    os.remove(_db_path)


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def admin_token(app):
    with app.app_context():
        user = User.query.filter_by(phone="03000000001").first()
        if not user:
            user = User(name="Test Admin", phone="03000000001", address="HQ",
                        password=generate_password_hash("supersecret8"), role="admin")
            db.session.add(user)
            db.session.commit()
        return create_access_token(identity=str(user.id),
                                   additional_claims={"role": "admin"})


@pytest.fixture()
def auth_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}
