from datetime import datetime
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
            "id":         self.id,
            "name":       self.name,
            "phone":      self.phone,
            "role":       self.role,
            "created_at": self.created_at.isoformat(),
        }


class Order(db.Model):
    __tablename__ = "orders"

    id               = db.Column(db.Integer, primary_key=True)
    # Guest info — no login required
    guest_name       = db.Column(db.String(120), nullable=False)
    guest_phone      = db.Column(db.String(20),  nullable=False)
    total_price      = db.Column(db.Float,       nullable=False)
    delivery_address = db.Column(db.Text,        nullable=False)
    status           = db.Column(db.String(20),  nullable=False, default="Pending")
    created_at       = db.Column(db.DateTime,    default=datetime.utcnow)

    items = db.relationship("OrderItem", backref="order", lazy=True, cascade="all, delete-orphan")

    def to_dict(self):
        return {
            "id":               self.id,
            "guest_name":       self.guest_name,
            "guest_phone":      self.guest_phone,
            "total_price":      self.total_price,
            "delivery_address": self.delivery_address,
            "status":           self.status,
            "created_at":       self.created_at.isoformat(),
            "items":            [item.to_dict() for item in self.items],
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
        d = {
            "id": self.id,
            "label": self.label,
            "desc": self.description,
            "folder": self.folder,
            "sort_order": self.sort_order,
        }
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
    image_file  = db.Column(db.String(255), nullable=False)
    dine_in     = db.Column(db.Boolean, default=True, nullable=False)
    takeaway    = db.Column(db.Boolean, default=True, nullable=False)
    delivery    = db.Column(db.Boolean, default=True, nullable=False)
    is_active   = db.Column(db.Boolean, default=True, nullable=False)
    sort_order  = db.Column(db.Integer, default=0)
    created_at  = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at  = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def image_path(self):
        folder = self.category.folder if self.category else ""
        return f"images/{folder}/{self.image_file}"

    def available_for(self, service):
        if service == "dinein":
            return self.dine_in
        if service == "takeaway":
            return self.takeaway
        if service == "delivery":
            return self.delivery
        return True

    def to_dict(self):
        return {
            "id": self.id,
            "category_id": self.category_id,
            "name": self.name,
            "price": self.price,
            "image_file": self.image_file,
            "image": self.image_path(),
            "dine_in": self.dine_in,
            "takeaway": self.takeaway,
            "delivery": self.delivery,
            "is_active": self.is_active,
            "sort_order": self.sort_order,
        }


class OrderItem(db.Model):
    __tablename__ = "order_items"

    id        = db.Column(db.Integer, primary_key=True)
    order_id  = db.Column(db.Integer, db.ForeignKey("orders.id"), nullable=False)
    item_name = db.Column(db.String(120), nullable=False)
    quantity  = db.Column(db.Integer,     nullable=False)
    price     = db.Column(db.Float,       nullable=False)

    def to_dict(self):
        return {
            "id":        self.id,
            "item_name": self.item_name,
            "quantity":  self.quantity,
            "price":     self.price,
            "subtotal":  round(self.quantity * self.price, 2),
        }
