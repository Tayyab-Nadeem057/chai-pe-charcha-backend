from flask import Blueprint, request, make_response
import json
from .. import db, limiter
from ..models import Order, OrderItem, MenuCategory, MenuItem
from ..utils import ok, err, clean_str, valid_phone, normalize_phone

user_bp = Blueprint("user", __name__)
VALID_SERVICES = {"delivery", "takeaway", "dinein"}


@user_bp.route("/menu", methods=["GET"])
def get_menu():
    service = clean_str(request.args.get("service"), 20).lower()
    if service and service not in VALID_SERVICES:
        return err("service must be delivery, takeaway, or dinein", 400)

    cats = MenuCategory.query.order_by(MenuCategory.sort_order).all()
    result = []
    for cat in cats:
        d = cat.to_dict(include_items=True, service=service or None)
        if d.get("items"):
            result.append(d)

    payload = json.dumps({"status": "success",
                          "data": {"categories": result, "service": service or "all"}})
    resp = make_response(payload)
    resp.headers["Content-Type"] = "application/json"
    # Short cache → multi-worker safe (no shared in-process cache needed) and
    # admin menu edits appear within ~30s. CDNs/browsers honour this.
    resp.headers["Cache-Control"] = "public, max-age=30, must-revalidate"
    return resp


@user_bp.route("/orders", methods=["POST"])
@limiter.limit("20 per minute; 200 per day")
def place_order():
    data    = request.get_json(silent=True) or {}
    name    = clean_str(data.get("name"), 120)
    phone   = clean_str(data.get("phone"), 20)
    address = clean_str(data.get("delivery_address"), 500)
    service = clean_str(data.get("service"), 20).lower() or "delivery"
    items   = data.get("items")

    if not name:
        return err("name is required", 400)
    if not valid_phone(phone):
        return err("A valid phone number is required", 400)
    if not address:
        return err("delivery_address is required", 400)
    if service not in VALID_SERVICES:
        return err("invalid service type", 400)
    if not isinstance(items, list) or not items:
        return err("items list is required and must not be empty", 400)
    if len(items) > 100:
        return err("too many items in a single order", 400)

    # ── Server-side pricing: prices come ONLY from the database ──
    validated = []
    total = 0.0
    for idx, raw in enumerate(items):
        if not isinstance(raw, dict):
            return err(f"items[{idx}] is malformed", 400)
        item_id = raw.get("item_id")
        variant = clean_str(raw.get("variant"), 40) or None
        qty     = raw.get("quantity")

        if not isinstance(qty, int) or not (1 <= qty <= 50):
            return err(f"items[{idx}].quantity must be an integer 1–50", 400)

        menu_item = db.session.get(MenuItem, item_id) if item_id is not None else None
        if not menu_item or not menu_item.is_active:
            return err(f"items[{idx}] is not available", 400)
        if menu_item.sold_out:
            return err(f"'{menu_item.name}' is sold out", 409)

        try:
            unit_price = menu_item.price_for_variant(variant)   # authoritative
        except ValueError as e:
            return err(str(e), 400)

        display_name = f"{menu_item.name} ({variant})" if variant else menu_item.name
        total += unit_price * qty
        validated.append({
            "item_id": menu_item.id, "item_name": display_name,
            "quantity": qty, "price": unit_price,
        })

    total = round(total, 2)

    order = Order(guest_name=name, guest_phone=normalize_phone(phone),
                  total_price=total, delivery_address=address,
                  service=service, status="Pending")
    db.session.add(order)
    db.session.flush()

    for v in validated:
        db.session.add(OrderItem(order_id=order.id, item_id=v["item_id"],
                                 item_name=v["item_name"], quantity=v["quantity"],
                                 price=v["price"]))
    db.session.commit()
    return ok(order.to_dict(), "Order placed successfully", 201)


@user_bp.route("/orders/<int:order_id>", methods=["GET"])
def get_order(order_id):
    """Public order tracking. Requires the matching phone number to view details
    (prevents enumerating other people's orders by ID)."""
    order = db.session.get(Order, order_id)
    if not order:
        return err("Order not found", 404)

    phone = request.args.get("phone")
    if phone and normalize_phone(phone) == order.guest_phone:
        return ok(order.to_dict())
    # Without phone proof, expose only non-sensitive status.
    return ok({"id": order.id, "status": order.status,
               "created_at": order.created_at.isoformat()})
