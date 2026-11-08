"""Session based authentication and role authorisation.

Passwords are never stored - only a salted hash produced by Werkzeug.
Every protected route is guarded on the server with a decorator, so hiding a
link in a template is never the thing that keeps a page private.
"""

from functools import wraps

from flask import flash, g, redirect, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

import db
from validators import EMAIL_PATTERN, ValidationError, parse_phone


# Where each role lands after logging in.
HOME_FOR_ROLE = {
    "user": "user.search",
    "provider": "provider.dashboard",
    "admin": "admin.dashboard",
}

# Used when a login email does not exist. Performing a real hash check in both
# cases makes the generic login error less useful as an account-enumeration
# timing signal.
_DUMMY_PASSWORD_HASH = generate_password_hash("not-a-real-account-password")


def hash_password(password):
    return generate_password_hash(password)


def verify_password(password_hash, password):
    try:
        return check_password_hash(password_hash, password)
    except (TypeError, ValueError):
        # A damaged legacy row must fail closed instead of causing a 500 page.
        return False


def verify_login_password(user, password):
    """Verify a login while doing equivalent hash work for an unknown email."""
    stored_hash = user["password_hash"] if user is not None else _DUMMY_PASSWORD_HASH
    # Registration never permits a password over 128 characters. Still perform
    # one bounded hash check so an oversized login cannot cause avoidable work.
    candidate = password if len(password) <= 128 else "invalid-oversized-password"
    valid = verify_password(stored_hash, candidate)
    return user is not None and len(password) <= 128 and valid


def validate_password(password, confirm):
    """The password policy, kept in one place.

    Used by registration, password change and password reset so the rules can
    never drift apart.
    """
    errors = []
    if not password or len(password) < 8:
        errors.append("Password must be at least 8 characters long.")
    elif len(password) > 128:
        errors.append("Password cannot be longer than 128 characters.")
    elif password.isdigit() or password.isalpha():
        errors.append("Password must mix letters and numbers.")
    if password != confirm:
        errors.append("The two passwords do not match.")
    return errors


def validate_registration(name, email, phone, password, confirm):
    """Return a list of problems with the submitted form. Empty means valid."""
    errors = []

    if not name or len(name.strip()) < 3:
        errors.append("Name must be at least 3 characters long.")
    if not EMAIL_PATTERN.match(email or ""):
        errors.append("Please enter a valid email address.")
    try:
        parse_phone(phone)
    except ValidationError as exc:
        errors.append(str(exc))
    errors.extend(validate_password(password, confirm))

    return errors


def login_user(user):
    """Start a session for this account."""
    session.clear()
    session["user_id"] = user["id"]
    session["role"] = user["role"]
    session["name"] = user["name"]
    session["auth_version"] = user["auth_version"]


def logout_user():
    session.clear()


def load_current_user():
    """Put the logged in account on `g` before every request.

    Re-reading the row each request means an account the admin just deactivated
    loses access immediately instead of keeping its old session privileges.
    """
    g.user = None
    user_id = session.get("user_id")
    if user_id is None:
        return

    user = db.fetch_one(
        "SELECT id, name, email, phone, role, is_active, auth_version "
        "FROM users WHERE id = %s",
        (user_id,),
    )
    if (user is None or not user["is_active"]
            or session.get("auth_version") != user["auth_version"]):
        session.clear()
        return

    g.user = user


def home_url_for(role):
    return url_for(HOME_FOR_ROLE.get(role, "user.search"))


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if g.get("user") is None:
            flash("Please log in to continue.", "error")
            return redirect(url_for("auth.login"))
        return view(*args, **kwargs)

    return wrapped


def role_required(*roles):
    """Allow the view only for the listed roles."""

    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            user = g.get("user")
            if user is None:
                flash("Please log in to continue.", "error")
                return redirect(url_for("auth.login"))
            if user["role"] not in roles:
                # Send them to their own area rather than showing a dead end.
                flash("You do not have access to that page.", "error")
                return redirect(home_url_for(user["role"]))
            return view(*args, **kwargs)

        return wrapped

    return decorator
