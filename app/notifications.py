"""WhatsApp/SMS sending. Pluggable: uses Twilio when configured, otherwise
falls back to logging the message (so you can develop/test without an account).

Three modes, chosen automatically by which env vars are set:

1. DEV (no Twilio vars)         -> logs the code to the console.
2. SANDBOX (Twilio + sandbox)   -> free-form WhatsApp message from the sandbox
                                   number. Good for testing with your own phone.
3. PRODUCTION (approved sender) -> sends via an approved WhatsApp TEMPLATE, which
                                   Meta requires for business-initiated messages.

Env vars:
    TWILIO_ACCOUNT_SID
    TWILIO_AUTH_TOKEN
    TWILIO_WHATSAPP_FROM     sandbox: whatsapp:+14155238886
                            production: whatsapp:+92XXXXXXXXXX (client's number)
    TWILIO_OTP_CONTENT_SID  (production only) the approved template's Content SID (HX...)
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


def _creds():
    return (os.environ.get("TWILIO_ACCOUNT_SID"),
            os.environ.get("TWILIO_AUTH_TOKEN"),
            os.environ.get("TWILIO_WHATSAPP_FROM"))


def _post(sid, token, params):
    url = f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json"
    data = urllib.parse.urlencode(params).encode()
    auth = base64.b64encode(f"{sid}:{token}".encode()).decode()
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Authorization", "Basic " + auth)
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode())


def send_otp(to_phone: str, code: str) -> bool:
    """Send a password-reset code. Returns True if actually sent via Twilio."""
    sid, token, wa_from = _creds()
    if not (sid and token and wa_from):
        print(f"[WhatsApp/dev] (configure Twilio to send for real) OTP for {to_phone}: {code}")
        return False

    to = "whatsapp:" + to_e164(to_phone)
    content_sid = os.environ.get("TWILIO_OTP_CONTENT_SID")
    try:
        if content_sid:
            # PRODUCTION: business-initiated messages must use an approved template.
            _post(sid, token, {
                "From": wa_from, "To": to,
                "ContentSid": content_sid,
                "ContentVariables": json.dumps({"1": code}),
            })
        else:
            # SANDBOX: free-form text is allowed.
            _post(sid, token, {
                "From": wa_from, "To": to,
                "Body": (f"Your Chai Pe Charcha verification code is {code}. "
                         f"It expires in 10 minutes. If you didn't request this, ignore it."),
            })
        return True
    except Exception as e:
        print(f"[WhatsApp] send failed: {e}")
        return False


# Backwards-compatible alias
def send_whatsapp(to_phone: str, body: str) -> bool:
    sid, token, wa_from = _creds()
    if not (sid and token and wa_from):
        print(f"[WhatsApp/dev] -> {to_phone}: {body}")
        return False
    try:
        _post(sid, token, {"From": wa_from, "To": "whatsapp:" + to_e164(to_phone), "Body": body})
        return True
    except Exception as e:
        print(f"[WhatsApp] send failed: {e}")
        return False
