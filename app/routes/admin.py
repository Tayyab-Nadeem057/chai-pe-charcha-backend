import os
import uuid
from functools import wraps
from flask import Blueprint, request, current_app
from werkzeug.security import generate_password_hash
from werkzeug.utils import secure_filename
from flask_jwt_extended import jwt_required, get_jwt, get_jwt_identity
from .. import db, limiter
from ..models import User, Order, MenuCategory, MenuItem
from ..utils import ok, err, clean_str, valid_phone, normalize_phone, valid_password

admin_bp = Blueprint("admin", __name__)
VALID_STATUSES = {"Pending", "Accepted", "Rejected"}


def admin_required(fn):
    @wraps(fn)
    @jwt_required()
    def wrapper(*args, **kwargs):
        if get_jwt().get("role") != "admin":
            return err("Admin access required", 403)
        return fn(*args, **kwargs)
    return wrapper


# ── ORDERS ────────────────────────────────────────────────────────
@admin_bp.route("/orders", methods=["GET"])
@admin_required
def get_all_orders():
    status   = request.args.get("status")
    page     = max(1, int(request.args.get("page", 1) or 1))
    per_page = min(100, max(1, int(request.args.get("per_page", 50) or 50)))
    query    = Order.query.order_by(Order.created_at.desc())
    if status and status in VALID_STATUSES:
        query = query.filter_by(status=status)
    p = query.paginate(page=page, per_page=per_page, error_out=False)
    return ok({"orders": [o.to_dict() for o in p.items],
               "total": p.total, "page": p.page, "pages": p.pages})


@admin_bp.route("/orders/<int:order_id>", methods=["GET"])
@admin_required
def get_order(order_id):
    order = db.session.get(Order, order_id)
    if not order:
        return err("Order not found", 404)
    return ok(order.to_dict())


@admin_bp.route("/orders/<int:order_id>", methods=["PUT"])
@admin_required
def update_order(order_id):
    order = db.session.get(Order, order_id)
    if not order:
        return err("Order not found", 404)
    status = clean_str((request.get_json(silent=True) or {}).get("status"), 20)
    if status not in VALID_STATUSES:
        return err(f"status must be one of: {', '.join(sorted(VALID_STATUSES))}", 400)
    order.status = status
    db.session.commit()
    return ok(order.to_dict(), f"Order {status.lower()} successfully")


@admin_bp.route("/stats", methods=["GET"])
@admin_required
def stats():
    return ok({
        "total_orders":    Order.query.count(),
        "pending_orders":  Order.query.filter_by(status="Pending").count(),
        "accepted_orders": Order.query.filter_by(status="Accepted").count(),
        "rejected_orders": Order.query.filter_by(status="Rejected").count(),
        "total_users":     User.query.count(),
    })


# ── STAFF / ADMIN ACCOUNTS ────────────────────────────────────────
@admin_bp.route("/users", methods=["GET"])
@admin_required
def get_users():
    users = User.query.order_by(User.created_at.desc()).all()
    return ok([u.to_dict() for u in users])


@admin_bp.route("/staff", methods=["POST"])
@admin_required
def create_staff():
    """Only an authenticated admin can create another admin account."""
    data     = request.get_json(silent=True) or {}
    name     = clean_str(data.get("name"), 120)
    phone    = clean_str(data.get("phone"), 20)
    address  = clean_str(data.get("address"), 500) or "—"
    password = data.get("password") or ""

    if not name:
        return err("name is required", 400)
    if not valid_phone(phone):
        return err("A valid Pakistani phone number is required", 400)
    if not valid_password(password):
        return err("Password must be at least 8 characters", 400)

    phone = normalize_phone(phone)
    if User.query.filter_by(phone=phone).first():
        return err("Phone number already registered", 409)

    user = User(name=name, phone=phone, address=address,
                password=generate_password_hash(password), role="admin")
    db.session.add(user)
    db.session.commit()
    return ok(user.to_dict(), "Staff account created", 201)


@admin_bp.route("/staff/<int:user_id>/reset-password", methods=["POST"])
@admin_required
def reset_staff_password(user_id):
    """Admin-controlled reset. Replaces the insecure name+phone self-reset."""
    new_password = (request.get_json(silent=True) or {}).get("new_password") or ""
    if not valid_password(new_password):
        return err("New password must be at least 8 characters", 400)
    target = db.session.get(User, user_id)
    if not target:
        return err("User not found", 404)
    target.password = generate_password_hash(new_password)
    db.session.commit()
    return ok(None, f"Password reset for {target.name}")


@admin_bp.route("/staff/<int:user_id>", methods=["DELETE"])
@admin_required
def delete_staff(user_id):
    if int(get_jwt_identity()) == user_id:
        return err("You cannot delete your own account", 400)
    if User.query.count() <= 1:
        return err("Cannot delete the last admin account", 400)
    target = db.session.get(User, user_id)
    if not target:
        return err("User not found", 404)
    db.session.delete(target)
    db.session.commit()
    return ok(None, "Staff account removed")


# ── MENU MANAGEMENT ───────────────────────────────────────────────
@admin_bp.route("/menu/categories", methods=["GET"])
@admin_required
def list_categories():
    cats = MenuCategory.query.order_by(MenuCategory.sort_order).all()
    return ok([c.to_dict(include_items=False) for c in cats])


@admin_bp.route("/menu/items", methods=["GET"])
@admin_required
def list_menu_items():
    q = MenuItem.query
    search   = clean_str(request.args.get("search"), 120).lower()
    category = clean_str(request.args.get("category"), 50)
    service  = clean_str(request.args.get("service"), 20).lower()
    active   = request.args.get("active")

    if search:
        q = q.filter(MenuItem.name.ilike(f"%{search}%"))
    if category:
        q = q.filter_by(category_id=category)
    if active == "1":
        q = q.filter_by(is_active=True)
    elif active == "0":
        q = q.filter_by(is_active=False)
    if service in {"dinein", "takeaway", "delivery"}:
        q = q.filter_by(**{{"dinein": "dine_in"}.get(service, service): True})

    items = q.order_by(MenuItem.category_id, MenuItem.sort_order).all()
    return ok([i.to_dict() for i in items])


def _parse_variants(raw):
    """Validate/normalize variant list: [{label, price_offset}]. Returns None or list."""
    if not raw:
        return None
    if not isinstance(raw, list):
        raise ValueError("variants must be a list")
    out = []
    for v in raw:
        label = clean_str((v or {}).get("label"), 40)
        if not label:
            raise ValueError("each variant needs a label")
        try:
            offset = round(float(v.get("price_offset", 0)), 2)
        except (TypeError, ValueError):
            raise ValueError("variant price_offset must be a number")
        out.append({"label": label, "price_offset": offset})
    return out or None


@admin_bp.route("/menu/items", methods=["POST"])
@admin_required
def create_menu_item():
    data        = request.get_json(silent=True) or {}
    name        = clean_str(data.get("name"), 120)
    category_id = clean_str(data.get("category_id"), 50)
    price       = data.get("price")

    if not name:
        return err("name is required", 400)
    if not category_id or not db.session.get(MenuCategory, category_id):
        return err("valid category_id is required", 400)
    try:
        price = round(float(price), 2)
        if price < 0:
            raise ValueError
    except (TypeError, ValueError):
        return err("valid price is required", 400)
    try:
        variants = _parse_variants(data.get("variants"))
    except ValueError as e:
        return err(str(e), 400)

    item = MenuItem(
        category_id=category_id, name=name, price=price,
        image_file=clean_str(data.get("image_file"), 255),
        image_url=clean_str(data.get("image_url"), 512) or None,
        variants=variants,
        dine_in=bool(data.get("dine_in", True)),
        takeaway=bool(data.get("takeaway", True)),
        delivery=bool(data.get("delivery", True)),
        is_active=bool(data.get("is_active", True)),
        sold_out=bool(data.get("sold_out", False)),
        sort_order=int(data.get("sort_order", 0) or 0),
    )
    db.session.add(item)
    db.session.commit()
    return ok(item.to_dict(), "Item created", 201)


@admin_bp.route("/menu/items/<int:item_id>", methods=["PUT"])
@admin_required
def update_menu_item(item_id):
    item = db.session.get(MenuItem, item_id)
    if not item:
        return err("Item not found", 404)
    data = request.get_json(silent=True) or {}

    if "name" in data:
        item.name = clean_str(data["name"], 120) or item.name
    if "category_id" in data:
        cid = clean_str(data["category_id"], 50)
        if not db.session.get(MenuCategory, cid):
            return err("invalid category_id", 400)
        item.category_id = cid
    if "price" in data:
        try:
            item.price = round(float(data["price"]), 2)
        except (TypeError, ValueError):
            return err("invalid price", 400)
    if "variants" in data:
        try:
            item.variants = _parse_variants(data["variants"])
        except ValueError as e:
            return err(str(e), 400)
    if "image_file" in data:
        item.image_file = clean_str(data["image_file"], 255) or item.image_file
    if "image_url" in data:
        item.image_url = clean_str(data["image_url"], 512) or None
    for flag in ("dine_in", "takeaway", "delivery", "is_active", "sold_out"):
        if flag in data:
            setattr(item, flag, bool(data[flag]))
    if "sort_order" in data:
        item.sort_order = int(data["sort_order"] or 0)

    db.session.commit()
    return ok(item.to_dict(), "Item updated")


@admin_bp.route("/menu/items/<int:item_id>", methods=["DELETE"])
@admin_required
def delete_menu_item(item_id):
    item = db.session.get(MenuItem, item_id)
    if not item:
        return err("Item not found", 404)
    db.session.delete(item)
    db.session.commit()
    return ok(None, "Item deleted")


# ── IMAGE UPLOAD ──────────────────────────────────────────────────
@admin_bp.route("/menu/upload", methods=["POST"])
@admin_required
@limiter.limit("60 per hour")
def upload_image():
    """Real multipart upload. Validates, re-encodes (strips metadata/payloads),
    compresses, and stores. Returns a URL to save on the item."""
    if "image" not in request.files:
        return err("No image file provided (field name: 'image')", 400)
    file = request.files["image"]
    if not file or file.filename == "":
        return err("Empty file", 400)

    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    if ext not in current_app.config["ALLOWED_IMAGE_EXTENSIONS"]:
        return err("Only JPG, PNG or WebP images are allowed", 400)

    try:
        from PIL import Image  # Pillow
    except ImportError:
        return err("Image processing unavailable on server (Pillow not installed)", 500)

    try:
        img = Image.open(file.stream)
        img.verify()                 # detect corrupt/non-image payloads
        file.stream.seek(0)
        img = Image.open(file.stream).convert("RGB")
    except Exception:
        return err("File is not a valid image", 400)

    # Resize to max 1000x1000 keeping aspect ratio, then compress.
    img.thumbnail((1000, 1000))
    fname = f"{uuid.uuid4().hex}.webp"
    dest  = os.path.join(current_app.config["UPLOAD_FOLDER"], secure_filename(fname))
    img.save(dest, "WEBP", quality=82, method=6)

    return ok({"image_url": f"/uploads/{fname}", "filename": fname}, "Image uploaded")
