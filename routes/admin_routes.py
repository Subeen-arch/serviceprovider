"""The administrator area: monitor the platform and manage what is on it."""

from flask import Blueprint, flash, redirect, render_template, request, url_for

import auth
import config
import db
import queries
from validators import ValidationError, clean_text

bp = Blueprint("admin", __name__, url_prefix="/admin")

BOOKING_STATUSES = ("pending", "accepted", "rejected", "completed", "cancelled")
PAYMENT_STATUSES = ("paid", "pending", "failed", "refunded")


@bp.route("/dashboard")
@auth.role_required("admin")
def dashboard():
    counts = db.fetch_one(
        "SELECT "
        " (SELECT COUNT(*) FROM users WHERE role = 'user')      AS customers,"
        " (SELECT COUNT(*) FROM users WHERE role = 'provider')  AS providers,"
        " (SELECT COUNT(*) FROM providers WHERE is_approved = 0) AS pending_approval,"
        " (SELECT COUNT(*) FROM services WHERE is_active = 1)   AS services,"
        " (SELECT COUNT(*) FROM bookings)                       AS bookings,"
        " (SELECT COUNT(*) FROM reviews)                        AS reviews,"
        " (SELECT COALESCE(SUM(amount), 0) FROM payments WHERE status = 'paid')"
        "                                                       AS paid_total,"
        " (SELECT COUNT(*) FROM payments WHERE status = 'paid')  AS paid_count"
    )

    by_status = db.fetch_all(
        "SELECT status, COUNT(*) AS total FROM bookings GROUP BY status"
    )
    status_counts = {status: 0 for status in BOOKING_STATUSES}
    for row in by_status:
        status_counts[row["status"]] = row["total"]

    recent = db.fetch_all(
        "SELECT b.id, b.scheduled_date, b.scheduled_time, b.status, "
        "s.name AS service_name, cu.name AS customer_name, p.business_name "
        "FROM bookings b "
        "JOIN services s  ON s.id = b.service_id "
        "JOIN users cu    ON cu.id = b.user_id "
        "JOIN providers p ON p.id = b.provider_id "
        "ORDER BY b.created_at DESC LIMIT 8"
    )

    popular = db.fetch_all(
        "SELECT s.id, s.name, s.icon, COUNT(b.id) AS total "
        "FROM services s LEFT JOIN bookings b ON b.service_id = s.id "
        "GROUP BY s.id, s.name, s.icon ORDER BY total DESC, s.name LIMIT 6"
    )

    return render_template(
        "admin/dashboard.html",
        counts=counts,
        status_counts=status_counts,
        recent=recent,
        popular=popular,
    )


# ------------------------------- users -------------------------------------
@bp.route("/users")
@auth.role_required("admin")
def users():
    # The dashboard's "Customers" card links here with ?role=user.
    role = request.args.get("role", "")
    if role not in ("user", "provider", "admin"):
        role = ""

    search = (request.args.get("search") or "").strip()

    sql = ("SELECT id, name, email, phone, role, is_active, created_at "
           "FROM users ")
    clauses, params = [], []
    if role:
        clauses.append("role = %s")
        params.append(role)
    if search:
        # Name, email or phone. Every value is still a query parameter, so a
        # search box can never become part of the SQL itself.
        clauses.append("(name LIKE %s OR email LIKE %s OR phone LIKE %s)")
        params.extend([queries.like_term(search)] * 3)
    if clauses:
        sql += "WHERE " + " AND ".join(clauses) + " "
    sql += "ORDER BY role, name"

    return render_template(
        "admin/users.html",
        users=db.fetch_all(sql, tuple(params)),
        active_role=role,
        search=search,
    )


@bp.post("/users/<int:user_id>/toggle")
@auth.role_required("admin")
def toggle_user(user_id):
    user = db.fetch_one("SELECT id, role, is_active FROM users WHERE id = %s", (user_id,))
    if user is None:
        flash("User not found.", "error")
        return redirect(url_for("admin.users"))

    # An admin must not be able to lock themselves - or another admin - out.
    if user["role"] == "admin":
        flash("Administrator accounts cannot be deactivated here.", "error")
        return redirect(url_for("admin.users"))

    new_state = 0 if user["is_active"] else 1
    db.execute("UPDATE users SET is_active = %s WHERE id = %s", (new_state, user_id))
    flash("Account activated." if new_state else "Account deactivated.", "success")
    return redirect(url_for("admin.users"))


# ----------------------------- providers -----------------------------------
@bp.route("/providers")
@auth.role_required("admin")
def providers():
    # The dashboard's "Waiting for approval" card links here with ?status=pending.
    status = request.args.get("status", "")
    if status not in ("pending", "approved"):
        status = ""

    search = (request.args.get("search") or "").strip()

    # The status filter and the search box are two separate conditions joined
    # with AND, so "Approved" plus "Carpenter" narrows to both.
    clauses, params = [], []
    if status == "pending":
        clauses.append("p.is_approved = 0")
    elif status == "approved":
        clauses.append("p.is_approved = 1")
    if search:
        clauses.append(
            "(p.business_name LIKE %s OR u.name LIKE %s OR u.email LIKE %s "
            "OR u.phone LIKE %s OR s.name LIKE %s OR p.address LIKE %s)"
        )
        params.extend([queries.like_term(search)] * 6)

    where = ("WHERE " + " AND ".join(clauses) + " ") if clauses else ""

    return render_template(
        "admin/providers.html",
        providers=db.fetch_all(
            "SELECT p.id, p.business_name, p.hourly_rate, p.experience_years, "
            "p.address, p.is_available, p.is_approved, "
            "u.name AS provider_name, u.email, u.phone, u.is_active AS account_active, "
            "s.name AS service_name, "
            "COALESCE(AVG(r.rating), 0) AS avg_rating, COUNT(r.id) AS review_count "
            "FROM providers p "
            "JOIN users u    ON u.id = p.user_id "
            "JOIN services s ON s.id = p.service_id "
            "LEFT JOIN reviews r ON r.provider_id = p.id "
            + where +
            "GROUP BY p.id, u.id, s.id "
            "ORDER BY p.is_approved, s.name, p.business_name",
            tuple(params),
        ),
        active_status=status,
        search=search,
    )


@bp.route("/providers/<int:provider_id>/location")
@auth.role_required("admin")
def provider_location(provider_id):
    """Where one provider works from, on its own map.

    Only this provider's row is fetched, so the page cannot show anyone else's
    address even by accident.
    """
    provider = db.fetch_one(
        "SELECT p.id, p.business_name, p.address, p.latitude, p.longitude, "
        "p.hourly_rate, p.experience_years, p.bio, p.is_available, p.is_approved, "
        "u.name AS provider_name, u.email, u.phone, u.is_active AS account_active, "
        "s.name AS service_name, s.icon AS service_icon, "
        "(SELECT COUNT(*) FROM bookings b WHERE b.provider_id = p.id) AS booking_count "
        "FROM providers p "
        "JOIN users u    ON u.id = p.user_id "
        "JOIN services s ON s.id = p.service_id "
        "WHERE p.id = %s",
        (provider_id,),
    )
    if provider is None:
        flash("Provider not found.", "error")
        return redirect(url_for("admin.providers"))

    return render_template(
        "admin/provider_location.html",
        provider=provider,
        galli_token=config.GALLI_ACCESS_TOKEN,
    )


@bp.post("/providers/<int:provider_id>/toggle")
@auth.role_required("admin")
def toggle_provider(provider_id):
    provider = db.fetch_one(
        "SELECT id, is_approved FROM providers WHERE id = %s", (provider_id,)
    )
    if provider is None:
        flash("Provider not found.", "error")
        return redirect(url_for("admin.providers"))

    new_state = 0 if provider["is_approved"] else 1
    db.execute(
        "UPDATE providers SET is_approved = %s WHERE id = %s", (new_state, provider_id)
    )
    flash(
        "Provider approved and now visible in search."
        if new_state
        else "Provider deactivated and hidden from search.",
        "success",
    )
    return redirect(url_for("admin.providers"))


# ------------------------------ services -----------------------------------
@bp.route("/services", methods=["GET", "POST"])
@auth.role_required("admin")
def services():
    if request.method == "POST":
        try:
            name = clean_text(request.form.get("name"), "Service name", 60, min_length=3)
            icon = clean_text(request.form.get("icon"), "Icon", 10, required=False)
            description = clean_text(
                request.form.get("description"), "Description", 255, required=False
            )
        except ValidationError as exc:
            flash(str(exc), "error")
            return redirect(url_for("admin.services"))

        if db.fetch_one("SELECT id FROM services WHERE name = %s", (name,)):
            flash("A service with that name already exists.", "error")
            return redirect(url_for("admin.services"))

        db.execute(
            "INSERT INTO services (name, icon, description) VALUES (%s, %s, %s)",
            (name, icon, description),
        )
        flash(f"Service '{name}' added.", "success")
        return redirect(url_for("admin.services"))

    return render_template(
        "admin/services.html",
        services=db.fetch_all(
            "SELECT s.id, s.name, s.icon, s.description, s.is_active, "
            "COUNT(DISTINCT p.id) AS provider_count "
            "FROM services s LEFT JOIN providers p ON p.service_id = s.id "
            "GROUP BY s.id ORDER BY s.name"
        ),
    )


@bp.route("/services/<int:service_id>/edit", methods=["GET", "POST"])
@auth.role_required("admin")
def edit_service(service_id):
    """Change a service's name, icon or description."""
    service = db.fetch_one(
        "SELECT id, name, icon, description, is_active FROM services WHERE id = %s",
        (service_id,),
    )
    if service is None:
        flash("Service not found.", "error")
        return redirect(url_for("admin.services"))

    if request.method == "POST":
        try:
            name = clean_text(request.form.get("name"), "Service name", 60, min_length=3)
            icon = clean_text(request.form.get("icon"), "Icon", 10, required=False)
            description = clean_text(
                request.form.get("description"), "Description", 255, required=False
            )
        except ValidationError as exc:
            flash(str(exc), "error")
            return redirect(url_for("admin.edit_service", service_id=service_id))

        # The name is UNIQUE in the database. Checking it here gives a readable
        # message instead of a MySQL error. The service's own row is excluded,
        # otherwise saving without renaming would look like a clash with itself.
        if db.fetch_one(
            "SELECT id FROM services WHERE name = %s AND id <> %s", (name, service_id)
        ):
            flash("Another service already uses that name.", "error")
            return redirect(url_for("admin.edit_service", service_id=service_id))

        db.execute(
            "UPDATE services SET name = %s, icon = %s, description = %s WHERE id = %s",
            (name, icon, description, service_id),
        )
        flash(f"Service '{name}' updated.", "success")
        return redirect(url_for("admin.services"))

    return render_template("admin/service_edit.html", service=service)


@bp.post("/services/<int:service_id>/delete")
@auth.role_required("admin")
def delete_service(service_id):
    """Remove a service, but only when nothing depends on it."""
    service = db.fetch_one("SELECT id, name FROM services WHERE id = %s", (service_id,))
    if service is None:
        flash("Service not found.", "error")
        return redirect(url_for("admin.services"))

    # providers.service_id and bookings.service_id are both ON DELETE RESTRICT,
    # so MySQL would refuse this anyway. Counting first turns that refusal into
    # a sentence the administrator can act on instead of a database error page.
    providers = db.fetch_one(
        "SELECT COUNT(*) AS total FROM providers WHERE service_id = %s", (service_id,)
    )["total"]
    bookings = db.fetch_one(
        "SELECT COUNT(*) AS total FROM bookings WHERE service_id = %s", (service_id,)
    )["total"]

    if providers or bookings:
        reasons = []
        if providers:
            reasons.append(f"{providers} provider{'s are' if providers != 1 else ' is'} "
                           "assigned to it")
        if bookings:
            reasons.append(f"{bookings} booking{'s' if bookings != 1 else ''} "
                           f"use{'' if bookings != 1 else 's'} it")
        flash(
            f"'{service['name']}' cannot be deleted because "
            + " and ".join(reasons)
            + ". Hide it instead - that takes it out of the customer search "
              "and keeps every existing record.",
            "error",
        )
        return redirect(url_for("admin.services"))

    db.execute("DELETE FROM services WHERE id = %s", (service_id,))
    flash(f"Service '{service['name']}' deleted.", "success")
    return redirect(url_for("admin.services"))


@bp.route("/services/<int:service_id>/providers")
@auth.role_required("admin")
def service_providers(service_id):
    """Only the providers who offer this one service.

    The filtering is done by the WHERE clause below, so the page never loads
    providers it is not going to show.
    """
    service = db.fetch_one(
        "SELECT id, name, icon, description, is_active FROM services WHERE id = %s",
        (service_id,),
    )
    if service is None:
        flash("Service not found.", "error")
        return redirect(url_for("admin.services"))

    return render_template(
        "admin/service_providers.html",
        service=service,
        providers=db.fetch_all(
            "SELECT p.id, p.business_name, p.hourly_rate, p.experience_years, "
            "p.address, p.is_available, p.is_approved, "
            "u.name AS provider_name, u.email, u.phone, u.is_active AS account_active, "
            "s.name AS service_name, "
            "COALESCE(AVG(r.rating), 0) AS avg_rating, COUNT(r.id) AS review_count "
            "FROM providers p "
            "JOIN users u    ON u.id = p.user_id "
            "JOIN services s ON s.id = p.service_id "
            "LEFT JOIN reviews r ON r.provider_id = p.id "
            "WHERE p.service_id = %s "
            "GROUP BY p.id, u.id, s.id "
            "ORDER BY p.is_approved, p.business_name",
            (service_id,),
        ),
    )


@bp.post("/services/<int:service_id>/toggle")
@auth.role_required("admin")
def toggle_service(service_id):
    service = db.fetch_one(
        "SELECT id, name, is_active FROM services WHERE id = %s", (service_id,)
    )
    if service is None:
        flash("Service not found.", "error")
        return redirect(url_for("admin.services"))

    new_state = 0 if service["is_active"] else 1
    db.execute("UPDATE services SET is_active = %s WHERE id = %s", (new_state, service_id))
    flash(
        f"'{service['name']}' is now {'available' if new_state else 'hidden'}.", "success"
    )
    return redirect(url_for("admin.services"))


# ------------------------------ bookings -----------------------------------
@bp.route("/bookings")
@auth.role_required("admin")
def bookings():
    status = request.args.get("status", "")
    # Only a known status is allowed to reach the query.
    if status not in BOOKING_STATUSES:
        status = ""

    # "Most booked services" links here with ?service_id=... - filtering on the
    # id rather than the display name, so a renamed service still works.
    service = None
    try:
        service_id = int(request.args.get("service_id", ""))
    except ValueError:
        service_id = None
    if service_id is not None:
        service = db.fetch_one(
            "SELECT id, name, icon FROM services WHERE id = %s", (service_id,)
        )
        if service is None:
            service_id = None

    sql = (
        "SELECT b.id, b.scheduled_date, b.scheduled_time, b.status, b.distance_km, "
        "b.address, s.name AS service_name, cu.name AS customer_name, "
        "cu.phone AS customer_phone, p.business_name, pu.name AS provider_name, "
        "pay.status AS payment_status, pay.amount AS payment_amount, "
        "pay.transaction_id AS payment_transaction_id "
        "FROM bookings b "
        "JOIN services s   ON s.id = b.service_id "
        "JOIN users cu     ON cu.id = b.user_id "
        "JOIN providers p  ON p.id = b.provider_id "
        "JOIN users pu     ON pu.id = p.user_id "
        "LEFT JOIN payments pay ON pay.booking_id = b.id "
    )

    search = (request.args.get("search") or "").strip()

    clauses, params = [], []
    if status:
        clauses.append("b.status = %s")
        params.append(status)
    if service_id is not None:
        clauses.append("b.service_id = %s")
        params.append(service_id)
    if search:
        # A booking number, or any of the names on the row. "BK1024", "#1024"
        # and "1024" all mean booking 1024.
        parts = ["cu.name LIKE %s", "pu.name LIKE %s", "p.business_name LIKE %s",
                 "s.name LIKE %s", "b.status LIKE %s", "b.address LIKE %s"]
        values = [queries.like_term(search)] * 6
        number = queries.booking_id_in(search)
        if number is not None:
            parts.append("b.id = %s")
            values.append(number)
        clauses.append("(" + " OR ".join(parts) + ")")
        params.extend(values)

    if clauses:
        sql += "WHERE " + " AND ".join(clauses) + " "
    sql += "ORDER BY b.created_at DESC LIMIT 200"

    return render_template(
        "admin/bookings.html",
        bookings=db.fetch_all(sql, tuple(params)),
        statuses=BOOKING_STATUSES,
        active_status=status,
        service=service,
        search=search,
    )


@bp.route("/bookings/<int:booking_id>")
@auth.role_required("admin")
def booking_detail(booking_id):
    booking = queries.get_booking(booking_id)
    if booking is None:
        flash("Booking not found.", "error")
        return redirect(url_for("admin.bookings"))
    return render_template(
        "admin/booking_detail.html",
        booking=booking,
        galli_token=config.GALLI_ACCESS_TOKEN,
    )


@bp.route("/messages")
@auth.role_required("admin")
def messages():
    """Everything sent through the Contact page, newest first."""
    unread_only = request.args.get("filter") == "unread"

    sql = (
        "SELECT m.id, m.name, m.email, m.subject, m.body, m.is_read, m.created_at, "
        "u.id AS account_id, u.role AS account_role "
        "FROM messages m LEFT JOIN users u ON u.id = m.user_id "
    )
    if unread_only:
        sql += "WHERE m.is_read = 0 "
    sql += "ORDER BY m.is_read ASC, m.created_at DESC LIMIT 200"

    counts = db.fetch_one(
        "SELECT COUNT(*) AS total, "
        "COALESCE(SUM(is_read = 0), 0) AS unread FROM messages"
    )

    return render_template(
        "admin/messages.html",
        messages=db.fetch_all(sql),
        counts=counts,
        unread_only=unread_only,
    )


@bp.post("/messages/<int:message_id>/read")
@auth.role_required("admin")
def toggle_message(message_id):
    """Mark one message read, or put it back to unread."""
    message = db.fetch_one(
        "SELECT id, is_read FROM messages WHERE id = %s", (message_id,)
    )
    if message is None:
        flash("Message not found.", "error")
        return redirect(url_for("admin.messages"))

    new_state = 0 if message["is_read"] else 1
    db.execute("UPDATE messages SET is_read = %s WHERE id = %s",
               (new_state, message_id))
    flash("Marked as read." if new_state else "Marked as unread.", "success")
    return redirect(request.referrer or url_for("admin.messages"))


@bp.post("/messages/<int:message_id>/delete")
@auth.role_required("admin")
def delete_message(message_id):
    """Remove a message once it has been dealt with."""
    if db.fetch_one("SELECT id FROM messages WHERE id = %s", (message_id,)) is None:
        flash("Message not found.", "error")
        return redirect(url_for("admin.messages"))

    db.execute("DELETE FROM messages WHERE id = %s", (message_id,))
    flash("Message deleted.", "success")
    return redirect(url_for("admin.messages"))


@bp.route("/reviews")
@auth.role_required("admin")
def reviews():
    """Every review, optionally only one star value, in a chosen order."""
    rating, sort = queries.read_review_filters(request.args)

    sql = (
        "SELECT rv.id, rv.rating, rv.comment, rv.created_at, rv.booking_id, "
        "cu.name AS customer_name, p.business_name, s.name AS service_name "
        "FROM reviews rv "
        "JOIN users cu    ON cu.id = rv.user_id "
        "JOIN providers p ON p.id = rv.provider_id "
        "JOIN bookings b  ON b.id = rv.booking_id "
        "JOIN services s  ON s.id = b.service_id "
    )
    params = []
    if rating:
        sql += "WHERE rv.rating = %s "
        params.append(rating)

    # The sort comes from a fixed table of allowed values, never from the URL
    # directly, so nothing typed in the address bar can reach the query.
    sql += f"ORDER BY {queries.REVIEW_SORTS[sort][1]} LIMIT 200"

    return render_template(
        "admin/reviews.html",
        reviews=db.fetch_all(sql, tuple(params)),
        summary=queries.rating_breakdown(),
        sorts=queries.REVIEW_SORTS,
        active_rating=rating,
        active_sort=sort,
    )


@bp.route("/payments")
@auth.role_required("admin")
def payments():
    status = request.args.get("status", "")
    if status not in PAYMENT_STATUSES:
        status = "paid"  # the dashboard's revenue card is about money received

    sql = (
        "SELECT pay.id, pay.amount, pay.status, pay.payment_method, "
        "pay.transaction_id, pay.paid_at, pay.refunded_at, pay.created_at, "
        "pay.booking_id, b.status AS booking_status, "
        "s.name AS service_name, cu.name AS customer_name, p.business_name "
        "FROM payments pay "
        "JOIN bookings b   ON b.id = pay.booking_id "
        "JOIN users cu     ON cu.id = pay.user_id "
        "JOIN providers p  ON p.id = b.provider_id "
        "JOIN services s   ON s.id = b.service_id "
        "WHERE pay.status = %s "
        "ORDER BY pay.created_at DESC LIMIT 200"
    )

    return render_template(
        "admin/payments.html",
        payments=db.fetch_all(sql, (status,)),
        statuses=PAYMENT_STATUSES,
        active_status=status,
        totals=db.fetch_all(
            "SELECT status, COUNT(*) AS count, COALESCE(SUM(amount), 0) AS total "
            "FROM payments GROUP BY status"
        ),
    )
