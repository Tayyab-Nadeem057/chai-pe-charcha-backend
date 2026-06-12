"""Security regression tests — these guard the Phase 0/1 fixes."""


# ── Authentication ────────────────────────────────────────────────
def test_no_public_registration(client):
    """The old vulnerable self-register-as-admin route must be gone."""
    r = client.post("/api/auth/register", json={
        "name": "Hacker", "phone": "03001112222",
        "address": "x", "password": "password123"})
    assert r.status_code == 404


def test_login_rejects_bad_credentials(client):
    r = client.post("/api/auth/login", json={"phone": "03000000001", "password": "wrong"})
    assert r.status_code == 401
    assert r.get_json()["success"] is False


def test_login_returns_token(client, app):
    from werkzeug.security import generate_password_hash
    from app import db
    from app.models import User
    with app.app_context():
        if not User.query.filter_by(phone="03009998877").first():
            db.session.add(User(name="Login User", phone="03009998877", address="HQ",
                                password=generate_password_hash("supersecret8"), role="admin"))
            db.session.commit()
    r = client.post("/api/auth/login", json={"phone": "03009998877", "password": "supersecret8"})
    assert r.status_code == 200
    assert r.get_json()["data"]["token"]


# ── Authorization ─────────────────────────────────────────────────
def test_admin_route_requires_auth(client):
    r = client.get("/api/admin/orders")
    assert r.status_code == 401


def test_non_admin_token_is_forbidden(client, app):
    from flask_jwt_extended import create_access_token
    with app.app_context():
        token = create_access_token(identity="999", additional_claims={"role": "user"})
    r = client.get("/api/admin/orders", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 403


def test_admin_can_list_orders(client, auth_headers):
    r = client.get("/api/admin/orders", headers=auth_headers)
    assert r.status_code == 200
    assert r.get_json()["success"] is True


# ── Server-side pricing (anti-tampering) ──────────────────────────
def _first_item(app, with_variant=False):
    from app.models import MenuItem
    with app.app_context():
        q = MenuItem.query
        items = q.all()
        for it in items:
            has_v = bool(it.variants)
            if has_v == with_variant:
                return it.id, it.price, (it.variants[1]["label"] if has_v else None), it.variants
        it = items[0]
        return it.id, it.price, None, it.variants


def test_price_tampering_is_ignored(client, app):
    item_id, real_price, _, variants = _first_item(app, with_variant=False)
    # Attacker submits price=1; server must charge the real DB price.
    r = client.post("/api/orders", json={
        "name": "Tamper", "phone": "03001234567", "delivery_address": "Test St",
        "service": "delivery",
        "items": [{"item_id": item_id, "quantity": 2, "price": 1}]})
    assert r.status_code == 201
    assert r.get_json()["data"]["total_price"] == round(real_price * 2, 2)


def test_variant_price_comes_from_db(client, app):
    item_id, base, variant_label, variants = _first_item(app, with_variant=True)
    offset = next(v["price_offset"] for v in variants if v["label"] == variant_label)
    r = client.post("/api/orders", json={
        "name": "V", "phone": "03001234567", "delivery_address": "St", "service": "dinein",
        "items": [{"item_id": item_id, "variant": variant_label, "quantity": 1, "price": 0}]})
    assert r.status_code == 201
    assert r.get_json()["data"]["total_price"] == round(base + offset, 2)


def test_missing_required_variant_rejected(client, app):
    item_id, _, _, variants = _first_item(app, with_variant=True)
    r = client.post("/api/orders", json={
        "name": "V", "phone": "03001234567", "delivery_address": "St", "service": "dinein",
        "items": [{"item_id": item_id, "quantity": 1}]})
    assert r.status_code == 400


def test_unknown_item_rejected(client):
    r = client.post("/api/orders", json={
        "name": "X", "phone": "03001234567", "delivery_address": "St",
        "items": [{"item_id": 99999999, "quantity": 1}]})
    assert r.status_code == 400


def test_invalid_quantity_rejected(client, app):
    item_id, *_ = _first_item(app)
    r = client.post("/api/orders", json={
        "name": "X", "phone": "03001234567", "delivery_address": "St",
        "items": [{"item_id": item_id, "quantity": 0}]})
    assert r.status_code == 400


def test_invalid_phone_rejected(client, app):
    item_id, *_ = _first_item(app)
    r = client.post("/api/orders", json={
        "name": "X", "phone": "12", "delivery_address": "St",
        "items": [{"item_id": item_id, "quantity": 1}]})
    assert r.status_code == 400


# ── Password reset (WhatsApp OTP) ─────────────────────────────────
def _seed_reset_user(app, phone, code, expired=False):
    from datetime import datetime, timedelta
    from werkzeug.security import generate_password_hash
    from app import db
    from app.models import User, PasswordReset
    with app.app_context():
        if not User.query.filter_by(phone=phone).first():
            db.session.add(User(name="Reset User", phone=phone, address="HQ",
                                password=generate_password_hash("oldpassword8"), role="admin"))
        PasswordReset.query.filter_by(phone=phone).delete()
        exp = datetime.utcnow() + timedelta(minutes=(-1 if expired else 10))
        db.session.add(PasswordReset(phone=phone, code_hash=generate_password_hash(code),
                                     expires_at=exp))
        db.session.commit()


def test_forgot_password_is_generic_for_unknown_phone(client):
    # Must not reveal whether a phone exists (anti-enumeration).
    r = client.post("/api/auth/forgot-password", json={"phone": "03009990000"})
    assert r.status_code == 200
    assert r.get_json()["success"] is True


def test_reset_with_valid_code_succeeds(client, app):
    _seed_reset_user(app, "03007770001", "123456")
    r = client.post("/api/auth/reset-password", json={
        "phone": "03007770001", "code": "123456", "new_password": "brandnew123"})
    assert r.status_code == 200
    # The new password now works
    login = client.post("/api/auth/login", json={"phone": "03007770001", "password": "brandnew123"})
    assert login.status_code == 200


def test_reset_with_wrong_code_fails(client, app):
    _seed_reset_user(app, "03007770002", "123456")
    r = client.post("/api/auth/reset-password", json={
        "phone": "03007770002", "code": "000000", "new_password": "brandnew123"})
    assert r.status_code == 400


def test_reset_with_expired_code_fails(client, app):
    _seed_reset_user(app, "03007770003", "123456", expired=True)
    r = client.post("/api/auth/reset-password", json={
        "phone": "03007770003", "code": "123456", "new_password": "brandnew123"})
    assert r.status_code == 400


def test_reset_short_password_rejected(client, app):
    _seed_reset_user(app, "03007770004", "123456")
    r = client.post("/api/auth/reset-password", json={
        "phone": "03007770004", "code": "123456", "new_password": "short"})
    assert r.status_code == 400
