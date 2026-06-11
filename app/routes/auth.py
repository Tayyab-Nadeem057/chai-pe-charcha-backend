from flask import Blueprint, request, jsonify
from werkzeug.security import check_password_hash, generate_password_hash
from flask_jwt_extended import (
    create_access_token, jwt_required, get_jwt_identity,
    set_access_cookies, unset_jwt_cookies,
)
from .. import db, limiter
from ..models import User
from ..utils import ok, err, clean_str, normalize_phone, valid_password

auth_bp = Blueprint("auth", __name__)

# NOTE: There is intentionally NO public /register route. Admin accounts are
# created only via create_admin.py (CLI) or the protected POST /api/admin/staff
# endpoint. Public self-registration as admin was a critical vulnerability.


@auth_bp.route("/login", methods=["POST"])
@limiter.limit("5 per minute; 30 per hour")
def login():
    data     = request.get_json(silent=True) or {}
    phone    = normalize_phone(clean_str(data.get("phone"), 20))
    password = data.get("password") or ""

    if not phone or not password:
        return err("phone and password are required", 400)

    user = User.query.filter_by(phone=phone).first()
    # Constant-ish work: always returns the same generic error to avoid user enumeration.
    if not user or not check_password_hash(user.password, password):
        return err("Invalid credentials", 401)

    token = create_access_token(identity=str(user.id),
                                additional_claims={"role": user.role})
    resp = jsonify({"success": True, "message": "Login successful",
                    "data": {"user": user.to_dict()}})
    set_access_cookies(resp, token)   # httpOnly cookie + CSRF cookie
    return resp, 200


@auth_bp.route("/logout", methods=["POST"])
def logout():
    resp = jsonify({"success": True, "message": "Logged out", "data": None})
    unset_jwt_cookies(resp)
    return resp, 200


@auth_bp.route("/me", methods=["GET"])
@jwt_required()
def me():
    user = db.session.get(User, int(get_jwt_identity()))
    if not user:
        return err("User not found", 404)
    return ok(user.to_dict())


@auth_bp.route("/change-password", methods=["POST"])
@jwt_required()
@limiter.limit("10 per hour")
def change_password():
    user_id      = get_jwt_identity()
    data         = request.get_json(silent=True) or {}
    old_password = data.get("old_password") or ""
    new_password = data.get("new_password") or ""

    if not old_password or not new_password:
        return err("old_password and new_password are required", 400)
    if not valid_password(new_password):
        return err("New password must be at least 8 characters", 400)

    user = db.session.get(User, int(user_id))
    if not user or not check_password_hash(user.password, old_password):
        return err("Current password is incorrect", 401)

    user.password = generate_password_hash(new_password)
    db.session.commit()
    return ok(None, "Password changed successfully")
