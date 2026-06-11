from datetime import datetime
from flask import has_request_context, request
from . import db


class User(db.Model):
    __tablename__ = "users"

    id         = db.Column(db.Integer, primary_key=True)
    name       = db.Column(db.String(120), nullable=False)
    phone      = db.Column(db.String(20),  nullable=False, unique=True)
    address    = db.Column(db.Text,        nullable=False)
    password   = db.Column(db.String(256), nullable=False)
    role       = db.Column(db.String(10),  nullable=False, default="admin")
    created_at = db.Column(db.DateTime,    default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id, "name": self.name, "phone": self.phone,
            "role": self.role, "created_at": self.created_at.isoformat(),
        }


class Order(db.Model):
    __tablename__ = "orders"

    id               = db.Column(db.Integer, primary_key=True)
    guest_name       = db.Column(db.String(120), nullable=False)
    guest_phone      = db.Column(db.String(20),  nullable=False)
    total_price      = db.Column(db.Float,       nullable=False)
    delivery_address = db.Column(db.Text,        nullable=False)
    service          = db.Column(db.String(20),  nullable=False, default="delivery")
    status           = db.Column(db.String(20),  nullable=False, default="Pending")
    created_at       = db.Column(db.DateTime,    default=datetime.utcnow)

    items = db.relationship("OrderItem", backref="order", lazy=True, cascade="all, delete-orphan")

    def to_dict(self):
        return {
            "id": self.id, "guest_name": self.guest_name, "guest_phone": self.guest_phone,
            "total_price": self.total_price, "delivery_address": self.delivery_address,
            "service": self.service, "status": self.status,
            "created_at": self.created_at.isoformat(),
            "items": [item.to_dict() for item in self.items],
        }


class MenuCategory(db.Model):
    __tablename__ = "menu_categories"

    id          = db.Column(db.String(50), primary_key=True)
    label       = db.Column(db.String(120), nullable=False)
    description = db.Column(db.Text, default="")
    folder      = db.Column(db.String(120), nullable=False)
    sort_order  = db.Column(db.Integer, default=0)

    items = db.relationship("MenuItem", backref="category", lazy=True, cascade="all, delete-orphan")

    def to_dict(self, include_items=True, service=None):
        d = {"id": self.id, "label": self.label, "desc": self.description,
             "folder": self.folder, "sort_order": self.sort_order}
        if include_items:
            items = [i for i in self.items if i.is_active]
            if service:
                items = [i for i in items if i.available_for(service)]
            items.sort(key=lambda x: x.sort_order)
            d["items"] = [i.to_dict() for i in items]
        return d


class MenuItem(db.Model):
    __tablename__ = "menu_items"

    id          = db.Column(db.Integer, primary_key=True)
    category_id = db.Column(db.String(50), db.ForeignKey("menu_categories.id"), nullable=False)
    name        = db.Column(db.String(120), nullable=False)
    price       = db.Column(db.Float, nullable=False)
    image_file  = db.Column(db.String(255), nullable=False, default="")
    image_url   = db.Column(db.String(512))  # set when image uploaded to backend/cloud
    # Variants: list of {"label": str, "price_offset": number}. NULL = no variants.
    variants    = db.Column(db.JSON)
    dine_in     = db.Column(db.Boolean, default=True, nullable=False)
    takeaway    = db.Column(db.Boolean, default=True, nullable=False)
    delivery    = db.Column(db.Boolean, default=True, nullable=False)
    is_active   = db.Column(db.Boolean, default=True, nullable=False)
    sold_out    = db.Column(db.Boolean, default=False, nullable=False)
    sort_order  = db.Column(db.Integer, default=0)
    created_at  = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at  = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def image_src(self):
        """Absolute URL for uploaded images; relative static path for legacy ones."""
        if self.image_url:
            if self.image_url.startswith("http"):
                return self.image_url
            if has_request_context():
                return request.host_url.rstrip("/") + self.image_url
            return self.image_url
        folder = self.category.folder if self.category else ""
        return f"images/{folder}/{self.image_file}"

    def available_for(self, service):
        return {"dinein": self.dine_in, "takeaway": self.takeaway,
                "delivery": self.delivery}.get(service, True)

    def price_for_variant(self, variant_label):
        """Authoritative price lookup. Raises ValueError on any mismatch."""
        if self.variants:
            if not variant_label:
                raise ValueError(f"'{self.name}' requires a variant selection")
            for v in self.variants:
                if v.get("label") == variant_label:
                    return round(float(self.price) + float(v.get("price_offset", 0)), 2)
            raise ValueError(f"Invalid variant '{variant_label}' for '{self.name}'")
        if variant_label:
            raise ValueError(f"'{self.name}' does not support variants")
        return round(float(self.price), 2)

    def to_dict(self):
        return {
            "id": self.id, "category_id": self.category_id, "name": self.name,
            "price": self.price, "image_file": self.image_file,
            "image": self.image_src(), "variants": self.variants or [],
            "dine_in": self.dine_in, "takeaway": self.takeaway, "delivery": self.delivery,
            "is_active": self.is_active, "sold_out": self.sold_out, "sort_order": self.sort_order,
        }


class OrderItem(db.Model):
    __tablename__ = "order_items"

    id        = db.Column(db.Integer, primary_key=True)
    order_id  = db.Column(db.Integer, db.ForeignKey("orders.id"), nullable=False)
    item_id   = db.Column(db.Integer, db.ForeignKey("menu_items.id"))
    item_name = db.Column(db.String(160), nullable=False)
    quantity  = db.Column(db.Integer, nullable=False)
    price     = db.Column(db.Float,   nullable=False)

    def to_dict(self):
        return {
            "id": self.id, "item_id": self.item_id, "item_name": self.item_name,
            "quantity": self.quantity, "price": self.price,
            "subtotal": round(self.quantity * self.price, 2),
        }
