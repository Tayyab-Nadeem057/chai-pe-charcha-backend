import os
from flask import Flask, jsonify, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from flask_jwt_extended import JWTManager
from flask_cors import CORS
from flask_compress import Compress
from flask_migrate import Migrate
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from config import Config

db       = SQLAlchemy()
jwt      = JWTManager()
compress = Compress()
migrate  = Migrate()
limiter  = Limiter(key_func=get_remote_address, default_limits=[])


def create_app(config_object=Config):
    app = Flask(__name__)
    app.config.from_object(config_object)

    # Gzip/brotli compress JSON + text responses automatically
    app.config['COMPRESS_MIMETYPES'] = ['application/json', 'text/html', 'text/css', 'text/javascript']
    app.config['COMPRESS_LEVEL'] = 6
    app.config['COMPRESS_MIN_SIZE'] = 500

    db.init_app(app)
    jwt.init_app(app)
    compress.init_app(app)
    migrate.init_app(app, db)
    limiter.init_app(app)

    # ── CORS: explicit origins only, credentials enabled for cookies ──
    origins = app.config.get("FRONTEND_ORIGINS") or [
        "http://localhost:5000", "http://127.0.0.1:5000",
        "http://localhost:5500", "http://127.0.0.1:5500",
    ]
    CORS(app, resources={r"/api/*": {"origins": origins}}, supports_credentials=True)

    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

    # ── JWT error handlers → JSON (so the frontend can redirect on 401) ──
    @jwt.unauthorized_loader
    def _missing_token(reason):
        return jsonify({"success": False, "message": "Authentication required"}), 401

    @jwt.invalid_token_loader
    def _invalid_token(reason):
        return jsonify({"success": False, "message": "Invalid session"}), 401

    @jwt.expired_token_loader
    def _expired_token(header, payload):
        return jsonify({"success": False, "message": "Session expired, please log in again"}), 401

    # ── Health-check routes ──
    @app.route("/")
    def index():
        return jsonify({"name": "Chai Pe Charcha API", "status": "online", "version": "2.0"}), 200

    @app.route("/api")
    def api_root():
        return jsonify({"name": "Chai Pe Charcha API", "status": "online"}), 200

    # ── Serve uploaded menu images ──
    @app.route("/uploads/<path:filename>")
    def uploaded_file(filename):
        resp = send_from_directory(app.config["UPLOAD_FOLDER"], filename)
        resp.headers["Cache-Control"] = "public, max-age=86400"
        return resp

    # ── Request body too large (file uploads) ──
    @app.errorhandler(413)
    def _too_large(e):
        return jsonify({"success": False, "message": "File too large (max 6 MB)"}), 413

    # Register blueprints
    from .routes.auth  import auth_bp
    from .routes.user  import user_bp
    from .routes.admin import admin_bp

    app.register_blueprint(auth_bp,  url_prefix="/api/auth")
    app.register_blueprint(user_bp,  url_prefix="/api")
    app.register_blueprint(admin_bp, url_prefix="/api/admin")

    # Create tables + seed menu (NOT an admin — admins are created explicitly).
    # In production with Postgres, prefer `flask db upgrade`. create_all() is a
    # safe no-op for already-migrated tables and keeps local SQLite dev simple.
    with app.app_context():
        db.create_all()
        _seed_menu()
        _bootstrap_admin()

    return app


def _bootstrap_admin():
    """Create the FIRST admin from env vars — only when no users exist yet.

    Secure one-time bootstrap so you never need the Render Shell:
      set BOOTSTRAP_ADMIN_PHONE + BOOTSTRAP_ADMIN_PASSWORD (and optionally
      BOOTSTRAP_ADMIN_NAME) → admin is created on the next deploy.
    Once an admin exists this is a no-op, so it's safe to leave configured.
    Delete BOOTSTRAP_ADMIN_PASSWORD afterwards as good hygiene.
    """
    from .models import User
    from .utils import valid_phone, normalize_phone, valid_password
    from werkzeug.security import generate_password_hash

    phone = (os.environ.get("BOOTSTRAP_ADMIN_PHONE") or "").strip()
    pw    = os.environ.get("BOOTSTRAP_ADMIN_PASSWORD") or ""
    name  = (os.environ.get("BOOTSTRAP_ADMIN_NAME") or "Admin").strip()

    if not phone or not pw:
        return                      # not configured — nothing to do
    if User.query.count() > 0:
        return                      # already have accounts — never overwrite
    if not valid_phone(phone):
        print("[WARN] BOOTSTRAP_ADMIN_PHONE is not a valid phone — skipping bootstrap")
        return
    if not valid_password(pw):
        print("[WARN] BOOTSTRAP_ADMIN_PASSWORD must be at least 8 chars — skipping bootstrap")
        return

    db.session.add(User(name=name, phone=normalize_phone(phone), address="—",
                        password=generate_password_hash(pw), role="admin"))
    db.session.commit()
    print(f"[OK] Bootstrap admin created (phone {normalize_phone(phone)}). "
          f"You can now delete BOOTSTRAP_ADMIN_PASSWORD from the environment.")


def _seed_menu():
    """One-time menu seed when the catalog is empty. No admin is ever seeded."""
    from .models import MenuCategory, MenuItem
    from .seed_menu import SEED_CATEGORIES, CAT_DEFAULTS, DEFAULT_FLAGS, VARIANT_MAP
    if MenuItem.query.first():
        return
    for sort_cat, cat_data in enumerate(SEED_CATEGORIES):
        cat = MenuCategory(
            id=cat_data["id"], label=cat_data["label"],
            description=cat_data["desc"], folder=cat_data["folder"],
            sort_order=sort_cat,
        )
        db.session.add(cat)
        flags = {**DEFAULT_FLAGS, **CAT_DEFAULTS.get(cat_data["id"], {})}
        variants = VARIANT_MAP.get(cat_data["id"])
        for i, (name, price, img) in enumerate(zip(
            cat_data["names"], cat_data["prices"], cat_data["images"]
        )):
            db.session.add(MenuItem(
                category_id=cat_data["id"], name=name, price=float(price),
                image_file=img, dine_in=flags["dine_in"], takeaway=flags["takeaway"],
                delivery=flags["delivery"], sort_order=i, variants=variants,
            ))
    db.session.commit()
    print(f"[OK] Menu seeded — {MenuItem.query.count()} items")
