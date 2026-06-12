"""WhatsApp/SMS sending. Pluggable: uses Twilio when configured, otherwise
falls back to logging the message (so you can develop/test without an account).

To go live, set these env vars (Twilio → WhatsApp):
    TWILIO_ACCOUNT_SID
    TWILIO_AUTH_TOKEN
    TWILIO_WHATSAPP_FROM   e.g. whatsapp:+14155238886  (Twilio sandbox or your number)
"""
import os
import base64
import json
import urllib.request
import urllib.parse


def to_e164(phone: str) -> str:
    """Convert a Pakistani number to E.164. 03021807669 -> +923021807669."""
    digits = "".join(c for c in (phone or "") if c.isdigit())
    if digits.startswith("0092"):
        digits = digits[4:]
    elif digits.startswith("92"):
        digits = digits[2:]
    elif digits.startswith("0"):
        digits = digits[1:]
    return "+92" + digits


def send_whatsapp(to_phone: str, body: str) -> bool:
    """Returns True if actually sent via Twilio, False if it only logged (dev mode)."""
    sid     = os.environ.get("TWILIO_ACCOUNT_SID")
    token   = os.environ.get("TWILIO_AUTH_TOKEN")
    wa_from = os.environ.get("TWILIO_WHATSAPP_FROM")

    if not (sid and token and wa_from):
        # Dev/test mode — no provider configured. Log so you can still test.
        print(f"[WhatsApp/dev] (configure Twilio to send for real) -> {to_phone}: {body}")
        return False

    to = "whatsapp:" + to_e164(to_phone)
    url = f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json"
    data = urllib.parse.urlencode({"From": wa_from, "To": to, "Body": body}).encode()
    auth = base64.b64encode(f"{sid}:{token}".encode()).decode()
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Authorization", "Basic " + auth)
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            json.loads(resp.read().decode())
        return True
    except Exception as e:
        print(f"[WhatsApp] send failed: {e}")
        return False
