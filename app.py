"""Service Provider - local service provider finder.

Start the application with:  python app.py
"""

from datetime import date, timedelta

from flask import (Flask, abort, flash, g, redirect, render_template,
                   request, url_for)

import auth
import config
import db
import queries
from algorithms.recommendation import DEFAULT_MODE, MODES
from validators import ValidationError, clean_text, parse_email
from routes.admin_routes import bp as admin_bp
from routes.auth_routes import bp as auth_bp
from routes.provider_routes import bp as provider_bp
from routes.user_routes import bp as user_bp

app = Flask(__name__)
app.secret_key = config.SECRET_KEY

# Session cookie hardening. SECURE is left off because the project runs over
# plain HTTP on localhost; it should be turned on behind HTTPS.
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=config.SESSION_COOKIE_SECURE,
)

app.register_blueprint(auth_bp)
app.register_blueprint(user_bp)
app.register_blueprint(provider_bp)
app.register_blueprint(admin_bp)

# Close the MySQL connection at the end of every request.
app.teardown_appcontext(db.close_db)


@app.before_request
def load_user():
    """Make the logged in account available to every route and template."""
    try:
        auth.load_current_user()
    except db.DatabaseError:
        # Handled by the error handler below when the route needs the database.
        g.user = None


@app.context_processor
def inject_globals():
    """Values every template can use, including the notification bell count."""
    user = g.get("user")
    unread = 0
    if user is not None:
        try:
            unread = queries.unread_notification_count(user["id"])
        except db.DatabaseError:
            # The bell is never worth failing a page over.
            unread = 0
    unread_messages = 0
    if user is not None and user["role"] == "admin":
        try:
            row = db.fetch_one(
                "SELECT COUNT(*) AS total FROM messages WHERE is_read = 0"
            )
            unread_messages = row["total"] if row else 0
        except db.DatabaseError:
            unread_messages = 0

    return {
        "current_user": user,
        "unread_notifications": unread,
        "unread_messages": unread_messages,
        # Used as the minimum value on booking date inputs.
        "today": date.today().isoformat(),
    }


@app.template_filter("hhmm")
def format_time(value):
    """Show a MySQL TIME as 14:30.

    The connector returns a TIME column as a timedelta, so it has to be
    converted rather than formatted directly.
    """
    if value is None:
        return ""
    if isinstance(value, timedelta):
        total_minutes = int(value.total_seconds()) // 60
        return f"{total_minutes // 60:02d}:{total_minutes % 60:02d}"
    return value.strftime("%H:%M")


@app.route("/")
def index():
    """Landing page. A logged in visitor goes straight to their own area."""
    if g.get("user"):
        return redirect(auth.home_url_for(g.user["role"]))

    try:
        services = queries.services_with_provider_counts()
        # A real preview, drawn from the reviews table. It ranks by reputation
        # only: a true recommendation score needs the visitor's location.
        preview = queries.top_rated_providers(limit=3)
    except db.DatabaseError:
        services, preview = [], []
    return render_template("index.html", services=services, preview=preview)


@app.route("/services")
def services_page():
    """Public catalogue of the service categories customers can search."""
    return render_template("services.html",
                           services=queries.services_with_provider_counts())


@app.route("/services/<int:service_id>")
def service_detail(service_id):
    """One trade: its figures, its best-rated providers, and a way to search."""
    service = queries.service_overview(service_id)
    if service is None:
        # Unknown or deactivated services are simply not there.
        abort(404)
    return render_template(
        "service_detail.html",
        service=service,
        top_providers=queries.top_rated_providers(service_id=service_id, limit=5),
        # The ranking panel quotes the algorithm's real default weights.
        weights=MODES[DEFAULT_MODE]["weights"],
    )


@app.route("/how-it-works")
def how_it_works():
    """Public explanation of the customer booking flow and core algorithms."""
    return render_template("how_it_works.html")


@app.route("/for-providers")
def for_providers():
    """Public introduction for tradespeople who want to join the platform."""
    return render_template("for_providers.html")


@app.route("/contact", methods=["GET", "POST"])
def contact():
    """Send a message to whoever runs the site.

    Open to everyone: a signed-in customer or provider gets their details
    filled in, and a visitor who is not signed in can still write in. The
    message is stored for the administrator to read - nothing is emailed,
    because the project has no mail server.
    """
    form = {}

    if request.method == "POST":
        form = request.form.to_dict()
        try:
            name = clean_text(request.form.get("name"), "Name", 80, min_length=3)
            email = parse_email(request.form.get("email"))
            subject = clean_text(request.form.get("subject"), "Subject", 120,
                                 required=False)
            body = clean_text(request.form.get("message"), "Message", 2000,
                              min_length=10)
        except ValidationError as exc:
            flash(str(exc), "error")
            return render_template("contact.html", form=form), 400

        db.execute(
            "INSERT INTO messages (user_id, name, email, subject, body) "
            "VALUES (%s, %s, %s, %s, %s)",
            (g.user["id"] if g.get("user") else None, name, email, subject, body),
        )
        flash(
            "Thank you - your message has been sent. The administrator will "
            "read it and can reply to you at " + email + ".",
            "success",
        )
        return redirect(url_for("contact"))

    # Save a signed-in person from typing what we already know.
    if g.get("user"):
        form = {"name": g.user["name"], "email": g.user["email"]}
    return render_template("contact.html", form=form)


# ------------------------------ error pages --------------------------------
@app.errorhandler(404)
def not_found(_error):
    return render_template(
        "error.html", code=404, message="We could not find that page."
    ), 404


@app.errorhandler(403)
def forbidden(_error):
    return render_template(
        "error.html", code=403, message="You do not have access to that page."
    ), 403


@app.errorhandler(db.DatabaseError)
def database_error(error):
    """Show a readable page instead of a stack trace when the database fails.

    A query that fails is usually a database built by an older version of
    schema.sql, so it gets its own advice rather than being blamed on MySQL
    being down.
    """
    app.logger.error("Database error: %s", error)

    if getattr(error, "connection_failed", False):
        message = ("Could not connect to the database. Check that MySQL is "
                   "running and that DB_USER / DB_PASSWORD in .env are correct.")
    else:
        message = ("The database rejected a query. This usually means the "
                   "tables are out of date - run  python setup_db.py  to bring "
                   "them up to date.")

    # In debug mode the real error is shown, so a problem can be fixed without
    # digging through the terminal. It is never shown to normal visitors.
    detail = str(error) if app.debug else None

    return render_template(
        "error.html", code=503, message=message, detail=detail
    ), 503


@app.errorhandler(500)
def server_error(error):
    app.logger.error("Unhandled error: %s", error)
    return render_template(
        "error.html", code=500, message="Something went wrong on our side."
    ), 500


def print_startup_summary():
    """Show which settings this process actually loaded.

    Settings are read once, when the process starts. Flask's auto-reloader
    re-launches a child process that inherits the parent's environment, so an
    edit to .env is NOT picked up by a reload - the server has to be stopped
    and started again. Printing the values here makes a stale process obvious
    instead of it quietly using the old ones.
    """
    def tail(secret):
        # Never print a whole secret - the last few characters are enough to
        # check it against the value you pasted into .env.
        return f"...{secret[-6:]}" if secret else "(not set)"

    print("Service Provider")
    print(f"  database : {config.DB_NAME} at {config.DB_HOST}:{config.DB_PORT} "
          f"as '{config.DB_USER}'")
    print(f"  map      : Galli Maps {tail(config.GALLI_ACCESS_TOKEN)}")
    print(f"  payments : Khalti {tail(config.KHALTI_SECRET_KEY)} "
          f"via {config.KHALTI_BASE_URL}")
    print("  (after editing .env, stop the server and start it again)")


if __name__ == "__main__":
    print_startup_summary()
    app.run(debug=True)
