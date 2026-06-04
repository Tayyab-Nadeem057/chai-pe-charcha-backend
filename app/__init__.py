from flask import Flask, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_jwt_extended import JWTManager
from flask_cors import CORS
from config import Config

db  = SQLAlchemy()
jwt = JWTManager()


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    db.init_app(app)
    jwt.init_app(app)
    CORS(app)

    # ── Health-check routes (stops 404 on base URL / Render pings) ──
    @app.route("/")
    def index():
        return jsonify({
            "name":    "Chai Pe Charcha API",
            "status":  "online",
            "version": "1.0",
            "docs":    {
                "menu":    "/api/menu",
                "orders":  "/api/orders",
                "login":   "/api/auth/login",
                "admin":   "/api/admin/orders",
            }
        }), 200

    @app.route("/api")
    def api_root():
        return jsonify({
            "name":    "Chai Pe Charcha API",
            "status":  "online",
            "endpoints": [
                "GET  /api/menu",
                "POST /api/orders",
                "GET  /api/orders/<id>",
                "POST /api/auth/login",
                "GET  /api/admin/orders  (JWT required)",
                "GET  /api/admin/stats   (JWT required)",
            ]
        }), 200

    # Register blueprints
    from .routes.auth   import auth_bp
    from .routes.user   import user_bp
    from .routes.admin  import admin_bp

    app.register_blueprint(auth_bp,  url_prefix="/api/auth")
    app.register_blueprint(user_bp,  url_prefix="/api")
    app.register_blueprint(admin_bp, url_prefix="/api/admin")

    # Create tables + seed default admin
    with app.app_context():
        db.create_all()
        _seed_admin()
        _seed_menu()

    return app


def _seed_admin():
    """Create a default admin account if none exists."""
    from .models import User
    from werkzeug.security import generate_password_hash
    if not User.query.filter_by(role="admin").first():
        admin = User(
            name="Admin",
            phone="0000000000",
            address="Chai Pe Charcha HQ",
            password=generate_password_hash("admin123"),
            role="admin",
        )
        db.session.add(admin)
        db.session.commit()
        print("[OK] Default admin created  ->  phone: 0000000000 | password: admin123")


def _seed_menu():
    from .models import MenuCategory, MenuItem
    from .seed_menu import SEED_CATEGORIES, CAT_DEFAULTS, DEFAULT_FLAGS
    if MenuItem.query.first():
        return
    sort_cat = 0
    for cat_data in SEED_CATEGORIES:
        cat = MenuCategory(
            id=cat_data["id"],
            label=cat_data["label"],
            description=cat_data["desc"],
            folder=cat_data["folder"],
            sort_order=sort_cat,
        )
        db.session.add(cat)
        flags = {**DEFAULT_FLAGS, **CAT_DEFAULTS.get(cat_data["id"], {})}
        for i, (name, price, img) in enumerate(zip(
            cat_data["names"], cat_data["prices"], cat_data["images"]
        )):
            db.session.add(MenuItem(
                category_id=cat_data["id"],
                name=name,
                price=float(price),
                image_file=img,
                dine_in=flags["dine_in"],
                takeaway=flags["takeaway"],
                delivery=flags["delivery"],
                sort_order=i,
            ))
        sort_cat += 1
    db.session.commit()
    print(f"[OK] Menu seeded — {MenuItem.query.count()} items")
