"""Khalti ePayment API v2 client.

Only two calls are needed:

    initiate()  - ask Khalti for a payment link, and get back a `pidx`
    lookup()    - ask Khalti what actually happened to that `pidx`

Both run server to server with the secret key in the Authorization header, so
the key never reaches the browser. Khalti's older checkout widget (the one that
takes a public key in JavaScript) is not used.

The important rule: after Khalti redirects the customer back, the query string
it adds - including `status=Completed` - is just text in a URL that anybody
could type. It is never trusted. Only the answer from lookup() decides whether
a payment happened.
"""

import requests

import config

TIMEOUT_SECONDS = 15

# Khalti's own wording for a finished payment. Nothing else counts as paid.
STATUS_COMPLETED = "Completed"


class KhaltiError(Exception):
    """Raised when Khalti cannot be reached or refuses the request."""


def is_configured():
    """False when no secret key is set, so the UI can say so honestly."""
    return bool(config.KHALTI_SECRET_KEY)


def rupees_to_paisa(rupees):
    """Khalti works in paisa, so Rs 850.00 has to be sent as 85000."""
    return int(round(float(rupees) * 100))


def paisa_to_rupees(paisa):
    return round(int(paisa) / 100, 2)


def _post(path, payload):
    """Send one authenticated request to Khalti and return the parsed JSON."""
    if not is_configured():
        raise KhaltiError("Khalti is not configured. Set KHALTI_SECRET_KEY in .env.")

    try:
        response = requests.post(
            f"{config.KHALTI_BASE_URL}/{path}",
            json=payload,
            headers={
                "Authorization": f"Key {config.KHALTI_SECRET_KEY}",
                "Content-Type": "application/json",
            },
            timeout=TIMEOUT_SECONDS,
        )
    except requests.RequestException as exc:
        raise KhaltiError(f"Could not reach Khalti: {exc}") from exc

    try:
        data = response.json()
    except ValueError:
        raise KhaltiError(f"Khalti returned an unreadable response ({response.status_code}).")

    if response.status_code >= 400:
        # Khalti reports problems as {"detail": ...} or as per-field messages.
        detail = data.get("detail")
        if not detail:
            detail = "; ".join(
                f"{field}: {', '.join(messages) if isinstance(messages, list) else messages}"
                for field, messages in data.items()
            )
        raise KhaltiError(detail or f"Khalti rejected the request ({response.status_code}).")

    return data


def initiate(amount_rupees, order_id, order_name, return_url, website_url, customer,
             product_name=None, breakdown_label=None):
    """Create a payment and return (pidx, payment_url).

    `order_id` must be unique for every attempt - Khalti will not let a `pidx`
    be reused, and neither will we.

    `product_name` and `breakdown_label` are what the customer actually reads on
    Khalti's payment page: they appear under "Product Summary" and "Amount
    Summary". `purchase_order_name` is *not* shown there, so the provider's
    business name has to be sent as a product for it to be visible.

    The breakdown has to add up to `amount` exactly or Khalti rejects the
    request, so only a single line is sent.
    """
    paisa = rupees_to_paisa(amount_rupees)

    payload = {
        "return_url": return_url,
        "website_url": website_url,
        "amount": paisa,
        "purchase_order_id": order_id,
        "purchase_order_name": order_name,
        "customer_info": {
            "name": customer.get("name", ""),
            "email": customer.get("email", ""),
            "phone": customer.get("phone", ""),
        },
    }

    if product_name:
        payload["product_details"] = [{
            "identity": str(order_id),
            "name": product_name,
            "total_price": paisa,
            "quantity": 1,
            "unit_price": paisa,
        }]
    if breakdown_label:
        payload["amount_breakdown"] = [{"label": breakdown_label, "amount": paisa}]

    data = _post("epayment/initiate/", payload)

    pidx = data.get("pidx")
    payment_url = data.get("payment_url")
    if not pidx or not payment_url:
        raise KhaltiError("Khalti did not return a payment link.")
    return pidx, payment_url


def lookup(pidx):
    """Ask Khalti for the real state of a payment.

    Returns a dictionary with `status`, `total_amount` (paisa) and
    `transaction_id`. This is the only thing allowed to mark a payment paid.
    """
    data = _post("epayment/lookup/", {"pidx": pidx})
    return {
        "status": data.get("status", ""),
        "total_amount": data.get("total_amount", 0),
        "transaction_id": data.get("transaction_id"),
        "refunded": bool(data.get("refunded")),
    }
