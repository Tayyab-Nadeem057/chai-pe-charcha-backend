from flask import Blueprint, request
from werkzeug.security import check_password_hash, generate_password_hash
from flask_jwt_extended import create_access_token
from .. import db
from ..models import User
from ..utils import ok, err

auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/register", methods=["POST"])
def register():
    data     = request.get_json(silent=True) or {}
    name     = (data.get("name")     or "").strip()
    phone    = (data.get("phone")    or "").strip()
    address  = (data.get("address")  or "").strip()
    password = (data.get("password") or "").strip()

    if not all([name, phone, address, password]):
        return err("name, phone, address and password are required", 400)
    if User.query.filter_by(phone=phone).first():
        return err("Phone number already registered", 409)

    user = User(name=name, phone=phone, address=address,
                password=generate_password_hash(password), role="admin")
    db.session.add(user)
    db.session.commit()
    return ok(user.to_dict(), "Registered successfully", 201)


@auth_bp.route("/login", methods=["POST"])
def login():
    data     = request.get_json(silent=True) or {}
    phone    = (data.get("phone")    or "").strip()
    password = (data.get("password") or "").strip()

    if not phone or not password:
        return err("phone and password are required", 400)

    user = User.query.filter_by(phone=phone).first()
    if not user or not check_password_hash(user.password, password):
        return err("Invalid credentials", 401)

    token = create_access_token(identity=str(user.id),
                                additional_claims={"role": user.role})
    return ok({"token": token, "user": user.to_dict()}, "Login successful")
