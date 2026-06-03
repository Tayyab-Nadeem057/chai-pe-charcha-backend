# Chai Pe Charcha — Backend API

A clean Flask REST API for the Chai Pe Charcha restaurant ordering system.

---

## 🚀 Quick Start

```bash
cd chai-pe-charcha-backend

# Install dependencies
pip install -r requirements.txt

# Run server
python run.py
# Server → http://localhost:5000
```

**Default admin account (auto-created on first run):**
| Field | Value |
|-------|-------|
| Phone | `0000000000` |
| Password | `admin123` |

---

## 📁 Project Structure

```
chai-pe-charcha-backend/
├── app/
│   ├── __init__.py       # App factory, DB init, admin seed
│   ├── models.py         # SQLAlchemy models (User, Order, OrderItem)
│   ├── utils.py          # ok() / err() response helpers
│   └── routes/
│       ├── auth.py       # Register & Login
│       ├── user.py       # Place & view orders
│       └── admin.py      # Manage orders, stats, users
├── config.py             # App config (DB URL, JWT secret)
├── run.py                # Entry point
└── requirements.txt
```

---

## 🗄️ Database Schema

### Users
| Column | Type | Notes |
|--------|------|-------|
| id | INTEGER PK | Auto-increment |
| name | VARCHAR(120) | Required |
| phone | VARCHAR(20) | Unique |
| address | TEXT | Required |
| password | VARCHAR(256) | Hashed (Werkzeug) |
| role | VARCHAR(10) | `user` or `admin` |
| created_at | DATETIME | Auto |

### Orders
| Column | Type | Notes |
|--------|------|-------|
| id | INTEGER PK | Auto-increment |
| user_id | FK → Users.id | Required |
| total_price | FLOAT | Auto-calculated |
| delivery_address | TEXT | Required |
| status | VARCHAR(20) | `Pending` / `Accepted` / `Rejected` |
| created_at | DATETIME | Auto |

### Order_Items
| Column | Type | Notes |
|--------|------|-------|
| id | INTEGER PK | Auto-increment |
| order_id | FK → Orders.id | Cascade delete |
| item_name | VARCHAR(120) | Required |
| quantity | INTEGER | ≥ 1 |
| price | FLOAT | Per unit |

---

## 🔌 API Reference

All responses follow this format:
```json
{
  "success": true,
  "message": "Order placed successfully",
  "data": { ... }
}
```

---

### Auth Endpoints

#### `POST /api/auth/register`
Register a new user.

**Body:**
```json
{
  "name": "Ali Khan",
  "phone": "03001234567",
  "address": "House 5, Block B, Karachi",
  "password": "mypassword"
}
```

---

#### `POST /api/auth/login`
Login and receive a JWT token.

**Body:**
```json
{ "phone": "03001234567", "password": "mypassword" }
```

**Response includes:**
```json
{ "token": "eyJ...", "user": { ... } }
```

> Use the token in all subsequent requests:
> `Authorization: Bearer <token>`

---

### User Endpoints *(require JWT)*

#### `POST /api/orders`
Place a new order.

**Body:**
```json
{
  "delivery_address": "House 5, Block B, Karachi",
  "items": [
    { "item_name": "Karak Chai", "quantity": 2, "price": 80 },
    { "item_name": "Samosa",     "quantity": 4, "price": 40 }
  ]
}
```

**Response:**
```json
{
  "success": true,
  "message": "Order placed successfully",
  "data": {
    "id": 1,
    "status": "Pending",
    "total_price": 320.0,
    "items": [ ... ]
  }
}
```

---

#### `GET /api/orders`
Get the current user's own orders.

---

#### `GET /api/orders/<id>`
Get a specific order by ID.

---

### Admin Endpoints *(require admin JWT)*

#### `GET /api/admin/orders`
Get all orders with pagination and optional status filter.

**Query params:**
- `?status=Pending` — filter by status
- `?page=1&per_page=20` — pagination

---

#### `GET /api/admin/orders/<id>`
Get a single order.

---

#### `PUT /api/admin/orders/<id>`
Update order status.

**Body:**
```json
{ "status": "Accepted" }
```
Valid values: `Pending`, `Accepted`, `Rejected`

---

#### `GET /api/admin/stats`
Dashboard stats.

**Response:**
```json
{
  "total_orders": 10,
  "pending_orders": 3,
  "accepted_orders": 6,
  "rejected_orders": 1,
  "total_users": 8
}
```

---

#### `GET /api/admin/users`
Get all registered users.

---

## 🔐 Security

- Passwords hashed using **Werkzeug PBKDF2-SHA256**
- Auth via **JWT** (Flask-JWT-Extended)
- Admin routes protected by `@admin_required` decorator
- Users can only view their own orders

---

## ⚙️ HTTP Status Codes

| Code | Meaning |
|------|---------|
| 200 | Success |
| 201 | Created |
| 400 | Bad Request / Validation Error |
| 401 | Unauthorized |
| 403 | Forbidden |
| 404 | Not Found |
| 409 | Conflict (duplicate phone) |
