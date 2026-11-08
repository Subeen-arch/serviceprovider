"""End-to-end password recovery checks against the isolated MySQL database."""

import os
import sys
from urllib.parse import urlparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tests import support

support.use_test_database()

import auth
import mailer
from app import app


results = support.Results("password reset")
check = results.check
email = support.CUSTOMER_EMAIL
original = support.q(
    "SELECT id, password_hash, auth_version FROM users WHERE email = %s", (email,)
)[0]
user_id = original["id"]
support.ex("DELETE FROM password_reset_tokens WHERE user_id = %s", (user_id,))

sent = []
real_sender = mailer.send_password_reset_email


def capture(recipient, name, reset_url):
    sent.append({"recipient": recipient, "name": name, "url": reset_url})


mailer.send_password_reset_email = capture

try:
    client = support.client()

    results.section("pages and request validation")
    response = client.get("/login", base_url=support.BASE)
    check("login offers forgot password", "/forgot-password" in support.body(response))
    response = client.get("/forgot-password", base_url=support.BASE)
    check("request form renders", response.status_code == 200 and "Send reset link" in support.body(response))
    response = client.post(
        "/forgot-password", data={"email": "not-an-email"},
        base_url=support.BASE,
    )
    check("invalid email is rejected", response.status_code == 400 and "valid email" in support.body(response))

    response = client.post(
        "/forgot-password", data={"email": "missing@example.com"},
        base_url=support.BASE, follow_redirects=True,
    )
    generic = "If an active account uses that email"
    check("unknown account gets generic response", response.status_code == 200 and generic in support.body(response))
    check("unknown account creates no token", not support.q("SELECT id FROM password_reset_tokens"))
    response = client.post(
        "/login",
        data={"email": "missing@example.com", "password": "not-a-real-account-password"},
        base_url=support.BASE,
    )
    check("dummy login hash can never authenticate", response.status_code == 401)

    results.section("token creation and delivery")
    response = client.post(
        "/forgot-password", data={"email": email.upper()},
        base_url=support.BASE, follow_redirects=True,
    )
    check("known account gets same generic response", response.status_code == 200 and generic in support.body(response))
    check("one reset email sent", len(sent) == 1 and sent[0]["recipient"] == email)
    reset_path = urlparse(sent[0]["url"]).path
    raw_token = reset_path.rsplit("/", 1)[-1]
    rows = support.q(
        "SELECT token_hash, expires_at, used_at FROM password_reset_tokens "
        "WHERE user_id = %s", (user_id,),
    )
    check("token is stored as a digest", len(rows) == 1 and rows[0]["token_hash"] != raw_token and len(rows[0]["token_hash"]) == 64)
    check("new token starts unused with an expiry", rows and rows[0]["used_at"] is None and rows[0]["expires_at"] is not None)

    client.post(
        "/forgot-password", data={"email": email},
        base_url=support.BASE, follow_redirects=True,
    )
    check("rapid repeat is throttled", len(sent) == 1)

    results.section("validation, reset, and login")
    response = client.get(reset_path, base_url=support.BASE)
    check("valid link opens reset form", response.status_code == 200 and "Confirm new password" in support.body(response))
    response = client.post(
        reset_path,
        data={"new_password": "Newpass123", "confirm_password": "Different123"},
        base_url=support.BASE,
    )
    check("confirmation mismatch rejected", response.status_code == 400 and "do not match" in support.body(response))
    check("validation failure does not consume token", support.q("SELECT used_at FROM password_reset_tokens WHERE user_id=%s", (user_id,))[0]["used_at"] is None)
    response = client.post(
        reset_path,
        data={"new_password": support.SEED_PASSWORD, "confirm_password": support.SEED_PASSWORD},
        base_url=support.BASE,
    )
    check("current password cannot be reused", response.status_code == 400 and "must be different" in support.body(response))

    existing_session = support.client(email)
    response = client.post(
        reset_path,
        data={"new_password": "Recovered123", "confirm_password": "Recovered123"},
        base_url=support.BASE, follow_redirects=False,
    )
    check("valid reset redirects to login", response.status_code == 302 and response.headers["Location"].endswith("/login"))
    changed = support.q("SELECT password_hash, auth_version FROM users WHERE id=%s", (user_id,))[0]
    check("new password is securely hashed", "Recovered123" not in changed["password_hash"] and auth.verify_password(changed["password_hash"], "Recovered123"))
    check("old password no longer works", support.client().post("/login", data={"email": email, "password": support.SEED_PASSWORD}, base_url=support.BASE).status_code == 401)
    check("new password logs in", support.client().post("/login", data={"email": email, "password": "Recovered123"}, base_url=support.BASE).status_code == 302)
    check("older sessions are revoked", "/login" in existing_session.get("/search", base_url=support.BASE).headers.get("Location", ""))
    response = client.get(reset_path, base_url=support.BASE)
    check("used link is rejected", response.status_code == 400 and "already been used" in support.body(response))

    results.section("invalid, expired, and undelivered links")
    response = client.get("/reset-password/not-a-real-token", base_url=support.BASE)
    check("invalid link is rejected", response.status_code == 400 and "Reset link invalid" in support.body(response))

    support.ex("DELETE FROM password_reset_tokens WHERE user_id=%s", (user_id,))
    sent.clear()
    client.post("/forgot-password", data={"email": email}, base_url=support.BASE)
    expired_path = urlparse(sent[0]["url"]).path
    support.ex(
        "UPDATE password_reset_tokens SET expires_at=DATE_SUB(UTC_TIMESTAMP(), INTERVAL 1 MINUTE) WHERE user_id=%s",
        (user_id,),
    )
    response = client.get(expired_path, base_url=support.BASE)
    check("expired link returns gone", response.status_code == 410 and "Reset link expired" in support.body(response))

    support.ex("DELETE FROM password_reset_tokens WHERE user_id=%s", (user_id,))

    def fail_delivery(*_args):
        raise mailer.MailDeliveryError("test SMTP failure")

    mailer.send_password_reset_email = fail_delivery
    response = client.post(
        "/forgot-password", data={"email": email},
        base_url=support.BASE, follow_redirects=True,
    )
    undelivered = support.q(
        "SELECT used_at FROM password_reset_tokens WHERE user_id=%s", (user_id,)
    )
    check("mail failure keeps generic response", response.status_code == 200 and generic in support.body(response))
    check("undelivered link is invalidated", undelivered and undelivered[0]["used_at"] is not None)

    results.section("unconfigured mail server")
    real_configured = mailer.is_configured
    mailer.is_configured = lambda: False
    try:
        before = support.q("SELECT COUNT(*) n FROM password_reset_tokens WHERE user_id=%s", (user_id,))[0]["n"]
        response = client.post("/forgot-password", data={"email": email}, base_url=support.BASE)
        text = support.body(response)
        check("says reset email is unavailable", response.status_code == 503 and "not available right now" in text)
        check("does not claim a link was sent", generic not in text)
        check("same answer for an unknown email",
              "not available right now" in support.body(client.post(
                  "/forgot-password", data={"email": "nobody@example.com"}, base_url=support.BASE)))
        after = support.q("SELECT COUNT(*) n FROM password_reset_tokens WHERE user_id=%s", (user_id,))[0]["n"]
        check("no token created", after == before)
    finally:
        mailer.is_configured = real_configured
    saved = (mailer.config.MAIL_SERVER, mailer.config.MAIL_FROM)
    try:
        mailer.config.MAIL_SERVER, mailer.config.MAIL_FROM = "smtp.example.com", "no-reply@example.com"
        check("the .env.example placeholder is not treated as configured", not mailer.is_configured())
        mailer.config.MAIL_SERVER, mailer.config.MAIL_FROM = "smtp.gmail.com", "someone@gmail.com"
        check("a real server is treated as configured", mailer.is_configured())
        mailer.config.MAIL_SERVER = ""
        check("an empty server is not configured", not mailer.is_configured())
    finally:
        mailer.config.MAIL_SERVER, mailer.config.MAIL_FROM = saved
finally:
    mailer.send_password_reset_email = real_sender
    support.ex("DELETE FROM password_reset_tokens WHERE user_id=%s", (user_id,))
    support.ex(
        "UPDATE users SET password_hash=%s, auth_version=%s WHERE id=%s",
        (original["password_hash"], original["auth_version"], user_id),
    )

raise SystemExit(1 if results.report() else 0)
