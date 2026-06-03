from functools import wraps
from flask import Blueprint, request
from flask_jwt_extended import jwt_required, get_jwt
from .. import db
from ..models import User, Order, MenuCategory, MenuItem
from ..utils import ok, err

admin_bp = Blueprint("admin", __name__)
VALID_STATUSES = {"Pending", "Accepted", "Rejected"}


def admin_required(fn):
    @wraps(fn)
    @jwt_required()
    def wrapper(*args, **kwargs):
        if get_jwt().get("role") != "admin":
            return err("Admin access required", 401)
        return fn(*args, **kwargs)
    return wrapper


@admin_bp.route("/orders", methods=["GET"])
@admin_required
def get_all_orders():
    status   = request.args.get("status")
    page     = int(request.args.get("page",     1))
    per_page = int(request.args.get("per_page", 50))
    query    = Order.query.order_by(Order.created_at.desc())
    if status and status in VALID_STATUSES:
        query = query.filter_by(status=status)
    p = query.paginate(page=page, per_page=per_page, error_out=False)
    return ok({"orders": [o.to_dict() for o in p.items],
               "total": p.total, "page": p.page, "pages": p.pages})


@admin_bp.route("/orders/<int:order_id>", methods=["GET"])
@admin_required
def get_order(order_id):
    order = Order.query.get(order_id)
    if not order:
        return err("Order not found", 404)
    return ok(order.to_dict())


@admin_bp.route("/orders/<int:order_id>", methods=["PUT"])
@admin_required
def update_order(order_id):
    order  = Order.query.get(order_id)
    if not order:
        return err("Order not found", 404)
    data   = request.get_json(silent=True) or {}
    status = (data.get("status") or "").strip()
    if not status:
        return err("status is required", 400)
    if status not in VALID_STATUSES:
        return err(f"status must be one of: {', '.join(VALID_STATUSES)}", 400)
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


@admin_bp.route("/users", methods=["GET"])
@admin_required
def get_users():
    users = User.query.order_by(User.created_at.desc()).all()
    return ok([u.to_dict() for u in users])


# ── MENU MANAGEMENT ──

@admin_bp.route("/menu/categories", methods=["GET"])
@admin_required
def list_categories():
    cats = MenuCategory.query.order_by(MenuCategory.sort_order).all()
    return ok([c.to_dict(include_items=False) for c in cats])


@admin_bp.route("/menu/items", methods=["GET"])
@admin_required
def list_menu_items():
    q = MenuItem.query
    search = (request.args.get("search") or "").strip().lower()
    category = (request.args.get("category") or "").strip()
    service = (request.args.get("service") or "").strip().lower()
    active = request.args.get("active")

    if search:
        q = q.filter(MenuItem.name.ilike(f"%{search}%"))
    if category:
        q = q.filter_by(category_id=category)
    if active == "1":
        q = q.filter_by(is_active=True)
    elif active == "0":
        q = q.filter_by(is_active=False)
    if service == "dinein":
        q = q.filter_by(dine_in=True)
    elif service == "takeaway":
        q = q.filter_by(takeaway=True)
    elif service == "delivery":
        q = q.filter_by(delivery=True)

    items = q.order_by(MenuItem.category_id, MenuItem.sort_order).all()
    return ok([i.to_dict() for i in items])


@admin_bp.route("/menu/items", methods=["POST"])
@admin_required
def create_menu_item():
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    category_id = (data.get("category_id") or "").strip()
    price = data.get("price")
    image_file = (data.get("image_file") or "").strip()

    if not name:
        return err("name is required", 400)
    if not category_id or not MenuCategory.query.get(category_id):
        return err("valid category_id is required", 400)
    if price is None or float(price) < 0:
        return err("valid price is required", 400)
    if not image_file:
        return err("image_file is required", 400)

    item = MenuItem(
        category_id=category_id,
        name=name,
        price=float(price),
        image_file=image_file,
        dine_in=bool(data.get("dine_in", True)),
        takeaway=bool(data.get("takeaway", True)),
        delivery=bool(data.get("delivery", True)),
        is_active=bool(data.get("is_active", True)),
        sort_order=int(data.get("sort_order", 0)),
    )
    db.session.add(item)
    db.session.commit()
    return ok(item.to_dict(), "Item created", 201)


@admin_bp.route("/menu/items/<int:item_id>", methods=["PUT"])
@admin_required
def update_menu_item(item_id):
    item = MenuItem.query.get(item_id)
    if not item:
        return err("Item not found", 404)
    data = request.get_json(silent=True) or {}

    if "name" in data:
        item.name = (data["name"] or "").strip() or item.name
    if "category_id" in data:
        cid = (data["category_id"] or "").strip()
        if not MenuCategory.query.get(cid):
            return err("invalid category_id", 400)
        item.category_id = cid
    if "price" in data:
        item.price = float(data["price"])
    if "image_file" in data:
        item.image_file = (data["image_file"] or "").strip() or item.image_file
    if "dine_in" in data:
        item.dine_in = bool(data["dine_in"])
    if "takeaway" in data:
        item.takeaway = bool(data["takeaway"])
    if "delivery" in data:
        item.delivery = bool(data["delivery"])
    if "is_active" in data:
        item.is_active = bool(data["is_active"])
    if "sort_order" in data:
        item.sort_order = int(data["sort_order"])

    db.session.commit()
    return ok(item.to_dict(), "Item updated")


@admin_bp.route("/menu/items/<int:item_id>", methods=["DELETE"])
@admin_required
def delete_menu_item(item_id):
    item = MenuItem.query.get(item_id)
    if not item:
        return err("Item not found", 404)
    db.session.delete(item)
    db.session.commit()
    return ok(None, "Item deleted")
