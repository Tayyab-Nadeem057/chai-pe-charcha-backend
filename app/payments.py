"""Safepay card-payment adapter (Pakistan).

Flow (Safepay hosted checkout):
  1. create_checkout(order) -> ask Safepay for a payment "tracker", return a
     checkout URL we redirect the customer to.
  2. Customer pays on Safepay's hosted page.
  3. Safepay calls our webhook (server-to-server) -> verify_webhook() confirms it,
     and we mark the order paid. We NEVER trust the browser for payment status.

NOTE: Card payments only activate when SAFEPAY_API_KEY + SAFEPAY_SECRET_KEY are set.
Until then, the frontend only offers Cash on Delivery. The exact Safepay endpoints
below follow their documented v3 checkout flow and should be confirmed against your
sandbox account before going live (https://apidocs.getsafepay.com/).
"""
import os
import json
import hmac
import hashlib
import urllib.request
import urllib.parse


def _base_url():
    env = os.environ.get("SAFEPAY_ENV", "sandbox")
    return ("https://sandbox.api.getsafepay.com" if env != "production"
            else "https://api.getsafepay.com")


def _checkout_host():
    env = os.environ.get("SAFEPAY_ENV", "sandbox")
    return ("https://sandbox.api.getsafepay.com" if env != "production"
            else "https://getsafepay.com")


def _post(path, payload, headers=None):
    url = _base_url() + path
    data = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode())


def create_checkout(order):
    """Returns a checkout URL to redirect the customer to, or raises on failure."""
    api_key = os.environ["SAFEPAY_API_KEY"]
    # 1. Create a payment tracker (amount is in the smallest currency unit).
    tracker = _post(
        "/order/payments/v3/",
        {
            "client": api_key,
            "amount": int(round(order.total_price * 100)),  # paisa
            "currency": "PKR",
            "environment": os.environ.get("SAFEPAY_ENV", "sandbox"),
            "metadata": {"order_id": order.id},
        },
    )
    token = (tracker.get("data") or {}).get("token") or tracker.get("token")
    if not token:
        raise RuntimeError(f"Safepay did not return a tracker token: {tracker}")

    # 2. Build the hosted-checkout URL.
    params = {
        "env": os.environ.get("SAFEPAY_ENV", "sandbox"),
        "beacon": token,
        "source": "custom",
        "order_id": str(order.id),
    }
    success = os.environ.get("PAYMENT_SUCCESS_URL")
    cancel = os.environ.get("PAYMENT_CANCEL_URL")
    if success:
        params["redirect_url"] = f"{success}?id={order.id}"
    if cancel:
        params["cancel_url"] = cancel
    return f"{_checkout_host()}/embedded/?{urllib.parse.urlencode(params)}", token


def verify_webhook(raw_body: bytes, signature: str) -> bool:
    """Verify the HMAC signature Safepay sends with the webhook."""
    secret = os.environ.get("SAFEPAY_WEBHOOK_SECRET", "")
    if not secret or not signature:
        return False
    expected = hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)
