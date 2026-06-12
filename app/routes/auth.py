import secrets
from datetime import datetime, timedelta
from flask import Blueprint, request, jsonify
from werkzeug.security import check_password_hash, generate_password_hash
from flask_jwt_extended import (
    create_access_token, jwt_required, get_jwt_identity,
)
from .. import db, limiter
from ..models import User, PasswordReset
from ..notifications import send_otp
from ..utils import ok, err, clean_str, normalize_phone, valid_phone, valid_password

auth_bp = Blueprint("auth", __name__)

RESET_CODE_TTL_MIN = 10
RESET_MAX_ATTEMPTS = 5

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
    return ok({"token": token, "user": user.to_dict()}, "Login successful")


@auth_bp.route("/logout", methods=["POST"])
def logout():
    # Stateless tokens: the client simply discards it. Endpoint kept for symmetry.
    return ok(None, "Logged out")


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


# ── Self-service password reset via WhatsApp OTP ──────────────────
@auth_bp.route("/forgot-password", methods=["POST"])
@limiter.limit("3 per 10 minutes; 10 per day")
def forgot_password():
    """Step 1: send a 6-digit code to the registered phone via WhatsApp.
    Always returns a generic success so attackers can't tell which phones exist."""
    phone = normalize_phone(clean_str((request.get_json(silent=True) or {}).get("phone"), 20))
    generic = ok(None, "If that number has an account, a reset code has been sent on WhatsApp.")

    if not phone:
        return generic
    user = User.query.filter_by(phone=phone).first()
    if not user:
        return generic  # don't reveal non-existence

    code = f"{secrets.randbelow(1_000_000):06d}"
    # Invalidate any previous codes for this phone
    PasswordReset.query.filter_by(phone=phone, used=False).update({"used": True})
    db.session.add(PasswordReset(
        phone=phone,
        code_hash=generate_password_hash(code),
        expires_at=datetime.utcnow() + timedelta(minutes=RESET_CODE_TTL_MIN),
    ))
    db.session.commit()

    send_otp(phone, code)
    return generic


@auth_bp.route("/reset-password", methods=["POST"])
@limiter.limit("10 per hour")
def reset_password():
    """Step 2: verify the code + set a new password."""
    data  = request.get_json(silent=True) or {}
    phone = normalize_phone(clean_str(data.get("phone"), 20))
    code  = clean_str(data.get("code"), 10)
    new_password = data.get("new_password") or ""

    if not phone or not code:
        return err("phone and code are required", 400)
    if not valid_password(new_password):
        return err("New password must be at least 8 characters", 400)

    pr = (PasswordReset.query
          .filter_by(phone=phone, used=False)
          .order_by(PasswordReset.created_at.desc())
          .first())
    if not pr or pr.expires_at < datetime.utcnow():
        return err("Invalid or expired code. Please request a new one.", 400)
    if pr.attempts >= RESET_MAX_ATTEMPTS:
        pr.used = True
        db.session.commit()
        return err("Too many attempts. Please request a new code.", 429)

    if not check_password_hash(pr.code_hash, code):
        pr.attempts += 1
        db.session.commit()
        return err("Incorrect code.", 400)

    user = User.query.filter_by(phone=phone).first()
    if not user:
        return err("Account not found", 404)

    user.password = generate_password_hash(new_password)
    pr.used = True
    db.session.commit()
    return ok(None, "Password reset successfully. You can now log in.")
