"""Registration, login, password recovery and logout."""

from datetime import datetime, timezone
import hashlib
import secrets

from flask import (
    Blueprint, current_app, flash, g, redirect, render_template, request,
    url_for,
)

import auth
import config
import db
import mailer
import queries
from validators import (
    ValidationError, clean_text, parse_coordinates, parse_email,
    parse_positive_number,
)

bp = Blueprint("auth", __name__)


@bp.route("/register", methods=["GET", "POST"])
def register():
    if g.user:
        return redirect(auth.home_url_for(g.user["role"]))

    services = queries.active_services()
    # Keeps what the visitor typed if the form has to be shown again. A public
    # "Join as a provider" link may preselect the provider option on first load.
    form = {"role": "provider"} if request.args.get("role") == "provider" else {}

    if request.method == "POST":
        form = request.form.to_dict()
        name = (request.form.get("name") or "").strip()
        email = (request.form.get("email") or "").strip().lower()
        phone = (request.form.get("phone") or "").strip()
        password = request.form.get("password") or ""
        confirm = request.form.get("confirm_password") or ""
        # Only these two roles can be created from the public form - an admin
        # account can never be self-registered.
        role = "provider" if request.form.get("role") == "provider" else "user"

        errors = auth.validate_registration(name, email, phone, password, confirm)

        provider_fields = None
        if role == "provider" and not errors:
            try:
                provider_fields = _read_provider_fields(request.form, services)
            except ValidationError as exc:
                errors.append(str(exc))

        if not errors and db.fetch_one(
            "SELECT id FROM users WHERE email = %s", (email,)
        ):
            errors.append("An account with that email already exists.")

        if errors:
            for message in errors:
                flash(message, "error")
            return render_template(
                "register.html", services=services, form=form,
                galli_token=config.GALLI_ACCESS_TOKEN,
            ), 400

        user_id = db.execute(
            "INSERT INTO users (name, email, phone, password_hash, role) "
            "VALUES (%s, %s, %s, %s, %s)",
            (name, email, phone, auth.hash_password(password), role),
        )

        if role == "provider":
            db.execute(
                "INSERT INTO providers (user_id, service_id, business_name, bio, "
                "hourly_rate, experience_years, address, latitude, longitude, "
                "is_available, is_approved) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 1, 0)",
                (
                    user_id,
                    provider_fields["service_id"],
                    provider_fields["business_name"],
                    provider_fields["bio"],
                    provider_fields["hourly_rate"],
                    provider_fields["experience_years"],
                    provider_fields["address"],
                    provider_fields["latitude"],
                    provider_fields["longitude"],
                ),
            )
            # A new provider cannot be found by customers until an
            # administrator approves them, so the administrator is told there
            # is something waiting rather than having to keep checking.
            queries.notify_admins(
                "New Provider Waiting for Approval",
                f"{provider_fields['business_name']} has registered and is "
                "waiting for approval.",
            )
            flash(
                "Account created. An administrator must approve your profile "
                "before customers can find you.",
                "success",
            )
        else:
            flash("Account created. Please log in.", "success")

        return redirect(url_for("auth.login"))

    return render_template(
        "register.html", services=services, form=form,
        galli_token=config.GALLI_ACCESS_TOKEN,
    )


def _read_provider_fields(form, services):
    """Validate the extra fields a provider has to supply at sign-up."""
    valid_service_ids = {s["id"] for s in services}
    try:
        service_id = int(form.get("service_id"))
    except (TypeError, ValueError):
        raise ValidationError("Please choose the service you provide.")
    if service_id not in valid_service_ids:
        raise ValidationError("Please choose a valid service.")

    lat, lng = parse_coordinates(form.get("latitude"), form.get("longitude"))

    return {
        "service_id": service_id,
        "business_name": clean_text(form.get("business_name"), "Business name", 100, min_length=3),
        "bio": clean_text(form.get("bio"), "About you", 500, required=False),
        "hourly_rate": parse_positive_number(form.get("hourly_rate"), "Hourly rate", 100000),
        "experience_years": int(parse_positive_number(form.get("experience_years"), "Experience", 60)),
        "address": clean_text(form.get("address"), "Work address", 150, min_length=3),
        "latitude": lat,
        "longitude": lng,
    }


@bp.route("/login", methods=["GET", "POST"])
def login():
    if g.user:
        return redirect(auth.home_url_for(g.user["role"]))

    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""

        user = db.fetch_one(
            "SELECT id, name, email, password_hash, role, is_active, auth_version "
            "FROM users WHERE email = %s",
            (email,),
        )

        # The same message for a wrong email and a wrong password, so the form
        # cannot be used to find out which emails are registered.
        if not auth.verify_login_password(user, password):
            flash("Incorrect email or password.", "error")
            return render_template("login.html", email=email), 401

        if not user["is_active"]:
            flash("This account has been deactivated. Please contact the administrator.", "error")
            return render_template("login.html", email=email), 403

        auth.login_user(user)
        flash(f"Welcome back, {user['name']}.", "success")
        return redirect(auth.home_url_for(user["role"]))

    return render_template("login.html", email="")


@bp.route("/login/admin", methods=["GET", "POST"])
def admin_login():
    """A separate way in for the administrator.

    It is the same session and the same password check as the ordinary login -
    only the extra role test at the end is different. Keeping one
    authentication system means there is only one place where a password is
    ever verified, which is what makes it safe to have two doors into it.
    """
    if g.user:
        return redirect(auth.home_url_for(g.user["role"]))

    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""

        user = db.fetch_one(
            "SELECT id, name, email, password_hash, role, is_active, auth_version "
            "FROM users WHERE email = %s",
            (email,),
        )

        # Same generic message as the ordinary login, so this page cannot be
        # used to find out which email addresses belong to an administrator.
        if not auth.verify_login_password(user, password):
            flash("Incorrect email or password.", "error")
            return render_template("admin_login.html", email=email), 401

        # The role test that makes this an administrator-only entrance. It runs
        # after the password has been checked, so it tells nothing to anyone
        # who does not already know a working password.
        if user["role"] != "admin":
            flash("This page is for administrators only. Please use the normal "
                  "login page for your account.", "error")
            return render_template("admin_login.html", email=email), 403

        if not user["is_active"]:
            flash("This account has been deactivated.", "error")
            return render_template("admin_login.html", email=email), 403

        auth.login_user(user)
        flash(f"Welcome back, {user['name']}.", "success")
        return redirect(url_for("admin.dashboard"))

    return render_template("admin_login.html", email="")


def _token_hash(token):
    """Return the value stored in MySQL; the bearer token itself is never stored."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _reset_token_row(token):
    """Find a reset request without accepting malformed tokens."""
    if not token or len(token) > 200:
        return None
    return db.fetch_one(
        "SELECT pr.id, pr.user_id, pr.expires_at, pr.used_at, "
        "u.password_hash, u.is_active "
        "FROM password_reset_tokens pr "
        "JOIN users u ON u.id = pr.user_id "
        "WHERE pr.token_hash = %s",
        (_token_hash(token),),
    )


def _token_problem(row):
    if row is None or row["used_at"] is not None or not row["is_active"]:
        return "invalid"
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    if row["expires_at"] <= now:
        return "expired"
    return None


@bp.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    """Email a short-lived reset link without revealing whether an email exists."""
    if g.user:
        return redirect(auth.home_url_for(g.user["role"]))

    email = ""
    if request.method == "POST":
        # A missing or placeholder mail server fails for every address, so
        # saying so reveals nothing about which accounts exist.
        if not mailer.is_configured():
            current_app.logger.error(
                "Password reset email is not configured: set MAIL_SERVER, "
                "MAIL_USERNAME, MAIL_PASSWORD and MAIL_FROM in .env"
            )
            flash("Password reset by email is not available right now. "
                  "Please contact the administrator.", "error")
            return render_template("forgot_password.html", email=email), 503

        try:
            email = parse_email(request.form.get("email"))
        except ValidationError as exc:
            flash(str(exc), "error")
            return render_template("forgot_password.html", email=email), 400

        user = db.fetch_one(
            "SELECT id, name, email FROM users "
            "WHERE email = %s AND is_active = 1",
            (email,),
        )

        if user is not None:
            # Do not let repeated submissions turn this endpoint into an email
            # flooder. The response remains identical in every case.
            recent = db.fetch_one(
                "SELECT id FROM password_reset_tokens "
                "WHERE user_id = %s AND used_at IS NULL "
                "AND created_at > DATE_SUB(UTC_TIMESTAMP(), INTERVAL 60 SECOND) "
                "LIMIT 1",
                (user["id"],),
            )
            if recent is None:
                token = secrets.token_urlsafe(32)
                db.execute(
                    "UPDATE password_reset_tokens SET used_at = UTC_TIMESTAMP() "
                    "WHERE user_id = %s AND used_at IS NULL",
                    (user["id"],),
                )
                reset_id = db.execute(
                    "INSERT INTO password_reset_tokens "
                    "(user_id, token_hash, expires_at) "
                    "VALUES (%s, %s, DATE_ADD(UTC_TIMESTAMP(), INTERVAL %s MINUTE))",
                    (user["id"], _token_hash(token), config.RESET_TOKEN_TTL_MINUTES),
                )
                reset_url = config.RESET_BASE_URL + url_for(
                    "auth.reset_password", token=token
                )
                try:
                    mailer.send_password_reset_email(
                        user["email"], user["name"], reset_url
                    )
                except mailer.MailDeliveryError as exc:
                    # A link that was never delivered should not remain usable.
                    db.execute(
                        "UPDATE password_reset_tokens SET used_at = UTC_TIMESTAMP() "
                        "WHERE id = %s",
                        (reset_id,),
                    )
                    current_app.logger.error(
                        "Could not send password reset email: %s", exc
                    )

        flash(
            "If an active account uses that email, a password reset link has "
            "been sent. Please check your inbox.",
            "success",
        )
        return redirect(url_for("auth.forgot_password"))

    return render_template("forgot_password.html", email=email)


@bp.route("/reset-password/<token>", methods=["GET", "POST"])
def reset_password(token):
    """Validate a one-time token and replace the account's password atomically."""
    if g.user:
        return redirect(auth.home_url_for(g.user["role"]))

    row = _reset_token_row(token)
    problem = _token_problem(row)
    if problem:
        status = 410 if problem == "expired" else 400
        return render_template("reset_password.html", token_valid=False,
                               expired=problem == "expired"), status

    if request.method == "POST":
        new_password = request.form.get("new_password") or ""
        confirm = request.form.get("confirm_password") or ""
        errors = auth.validate_password(new_password, confirm)
        if auth.verify_password(row["password_hash"], new_password):
            errors.append("The new password must be different from the current one.")
        if errors:
            for message in errors:
                flash(message, "error")
            return render_template("reset_password.html", token_valid=True), 400

        locked = None
        with db.transaction() as connection:
            with connection.cursor(dictionary=True) as cursor:
                # Lock and re-check inside the transaction so two simultaneous
                # submissions cannot consume the same link twice.
                cursor.execute(
                    "SELECT pr.id, pr.user_id FROM password_reset_tokens pr "
                    "JOIN users u ON u.id = pr.user_id "
                    "WHERE pr.token_hash = %s AND pr.used_at IS NULL "
                    "AND pr.expires_at > UTC_TIMESTAMP() AND u.is_active = 1 "
                    "FOR UPDATE",
                    (_token_hash(token),),
                )
                locked = cursor.fetchone()
                if locked is not None:
                    cursor.execute(
                        "UPDATE users SET password_hash = %s, "
                        "auth_version = auth_version + 1 WHERE id = %s",
                        (auth.hash_password(new_password), locked["user_id"]),
                    )
                    cursor.execute(
                        "UPDATE password_reset_tokens "
                        "SET used_at = UTC_TIMESTAMP() "
                        "WHERE user_id = %s AND used_at IS NULL",
                        (locked["user_id"],),
                    )

        if locked is None:
            return render_template(
                "reset_password.html", token_valid=False, expired=False
            ), 400

        # Clear any session cookie on this browser before returning to login.
        auth.logout_user()
        flash("Your password has been reset. You can now log in.", "success")
        return redirect(url_for("auth.login"))

    return render_template("reset_password.html", token_valid=True)


@bp.post("/logout")
@auth.login_required
def logout():
    auth.logout_user()
    flash("You have been logged out.", "success")
    return redirect(url_for("index"))
