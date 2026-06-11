#!/usr/bin/env python
"""
Securely create an admin account. This is the ONLY way to bootstrap the first
admin (public self-registration was removed).

Usage:
    python create_admin.py                 # interactive prompts
    python create_admin.py --name "Owner" --phone 03001234567

The password is read without echo and never logged.
"""
import argparse
import getpass
import sys

from app import create_app, db
from app.models import User
from app.utils import valid_phone, normalize_phone, valid_password
from werkzeug.security import generate_password_hash


def main():
    ap = argparse.ArgumentParser(description="Create a Chai Pe Charcha admin account")
    ap.add_argument("--name")
    ap.add_argument("--phone")
    ap.add_argument("--address", default="—")
    args = ap.parse_args()

    name  = args.name  or input("Admin name: ").strip()
    phone = args.phone or input("Phone (03XXXXXXXXX): ").strip()

    if not name:
        sys.exit("Name is required.")
    if not valid_phone(phone):
        sys.exit("Invalid Pakistani phone number.")

    pw1 = getpass.getpass("Password (min 8 chars): ")
    pw2 = getpass.getpass("Confirm password: ")
    if pw1 != pw2:
        sys.exit("Passwords do not match.")
    if not valid_password(pw1):
        sys.exit("Password must be at least 8 characters.")

    app = create_app()
    with app.app_context():
        phone_n = normalize_phone(phone)
        if User.query.filter_by(phone=phone_n).first():
            sys.exit("An account with that phone already exists.")
        user = User(name=name, phone=phone_n, address=args.address,
                    password=generate_password_hash(pw1), role="admin")
        db.session.add(user)
        db.session.commit()
        print(f"[OK] Admin '{name}' created (phone {phone_n}).")


if __name__ == "__main__":
    main()
