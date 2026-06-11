import re
from flask import jsonify


def ok(data=None, message="Success", code=200):
    return jsonify({"success": True, "message": message, "data": data}), code


def err(message="Error", code=400, data=None):
    return jsonify({"success": False, "message": message, "data": data}), code


# ── Validation helpers ────────────────────────────────────────────
# Pakistani mobile formats: 03XXXXXXXXX or +923XXXXXXXXX / 00923...
_PHONE_RE = re.compile(r"^(?:\+92|0092|92|0)?3\d{9}$")


def clean_str(value, max_len):
    """Trim and hard-cap a string field. Returns '' for non-strings."""
    if not isinstance(value, str):
        return ""
    return value.strip()[:max_len]


def valid_phone(phone):
    digits = re.sub(r"[\s\-()]", "", phone or "")
    return bool(_PHONE_RE.match(digits))


def normalize_phone(phone):
    """Store phones consistently as 0XXXXXXXXXX."""
    digits = re.sub(r"\D", "", phone or "")
    if digits.startswith("0092"):
        digits = digits[4:]
    elif digits.startswith("92"):
        digits = digits[2:]
    if not digits.startswith("0"):
        digits = "0" + digits
    return digits


def valid_password(pw):
    return isinstance(pw, str) and len(pw) >= 8
