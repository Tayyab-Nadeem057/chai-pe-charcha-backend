from flask import Blueprint, request
from .. import db
from ..models import Order, OrderItem, MenuCategory
from ..utils import ok, err

user_bp = Blueprint("user", __name__)
VALID_SERVICES = {"delivery", "takeaway", "dinein"}


@user_bp.route("/menu", methods=["GET"])
def get_menu():
    service = (request.args.get("service") or "").strip().lower()
    if service and service not in VALID_SERVICES:
        return err("service must be delivery, takeaway, or dinein", 400)
    cats = MenuCategory.query.order_by(MenuCategory.sort_order).all()
    result = []
    for cat in cats:
        d = cat.to_dict(include_items=True, service=service or None)
        if d.get("items"):
            result.append(d)
    return ok({"categories": result, "service": service or "all"})


@user_bp.route("/orders", methods=["POST"])
def place_order():
    data    = request.get_json(silent=True) or {}
    name    = (data.get("name")             or "").strip()
    phone   = (data.get("phone")            or "").strip()
    address = (data.get("delivery_address") or "").strip()
    items   = data.get("items")

    if not name:    return err("name is required", 400)
    if not phone:   return err("phone is required", 400)
    if not address: return err("delivery_address is required", 400)
    if not items or not isinstance(items, list) or len(items) == 0:
        return err("items list is required and must not be empty", 400)

    validated = []
    for idx, item in enumerate(items):
        iname    = (item.get("item_name") or "").strip()
        quantity = item.get("quantity")
        price    = item.get("price")
        if not iname:
            return err(f"items[{idx}].item_name is required", 400)
        if not isinstance(quantity, int) or quantity < 1:
            return err(f"items[{idx}].quantity must be a positive integer", 400)
        if not isinstance(price, (int, float)) or price < 0:
            return err(f"items[{idx}].price must be non-negative", 400)
        validated.append({"item_name": iname, "quantity": quantity, "price": float(price)})

    total = round(sum(i["quantity"] * i["price"] for i in validated), 2)

    order = Order(guest_name=name, guest_phone=phone,
                  total_price=total, delivery_address=address, status="Pending")
    db.session.add(order)
    db.session.flush()

    for i in validated:
        db.session.add(OrderItem(order_id=order.id,
                                 item_name=i["item_name"],
                                 quantity=i["quantity"],
                                 price=i["price"]))
    db.session.commit()
    return ok(order.to_dict(), "Order placed successfully", 201)


@user_bp.route("/orders/<int:order_id>", methods=["GET"])
def get_order(order_id):
    order = Order.query.get(order_id)
    if not order:
        return err("Order not found", 404)
    return ok(order.to_dict())
