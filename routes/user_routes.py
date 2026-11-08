"""The customer journey: find a service, pick a location, compare, book, review."""

from uuid import uuid4

import requests
from flask import (
    Blueprint, flash, g, jsonify, redirect, render_template, request, session,
    url_for,
)

import auth
import config
import db
import khalti
import queries
from algorithms.dijkstra import RouteFinder, haversine_km
from algorithms.recommendation import MODES, rank_providers, resolve_mode
from validators import (
    ValidationError, clean_text, parse_coordinates, parse_phone, parse_rating,
    parse_schedule,
)

bp = Blueprint("user", __name__)

def read_budget(raw):
    """Optional 'most I want to pay per hour'. Anything unusable means no budget."""
    if raw is None or str(raw).strip() == "":
        return None
    try:
        budget = float(raw)
    except (TypeError, ValueError):
        return None
    return budget if budget > 0 else None


@bp.route("/search")
@auth.role_required("user")
def search():
    """Service selection, map location picking, and the ranked results.

    One page with two states: before a location is chosen it is a form, after
    that the same page also shows the ranked providers underneath.
    """
    services = queries.active_services()

    raw_service = request.args.get("service_id")
    raw_lat = request.args.get("latitude")
    raw_lng = request.args.get("longitude")
    address = (request.args.get("address") or "").strip()
    # "sort" is still accepted so older links keep working.
    mode = resolve_mode(request.args.get("mode") or request.args.get("sort"))
    budget = read_budget(request.args.get("budget"))

    context = {
        "services": services,
        "galli_token": config.GALLI_ACCESS_TOKEN,
        "map_center": (config.DEFAULT_MAP_CENTER_LAT, config.DEFAULT_MAP_CENTER_LNG),
        "modes": MODES,
        "mode": mode,
        "weights": MODES[mode]["weights"],
        "budget": budget,
        "address": address,
        "searched": False,
        "selected_service": None,
        "latitude": None,
        "longitude": None,
        "providers": [],
        "unreachable": [],
    }

    # Nothing submitted yet - just show the form.
    if not (raw_service and raw_lat and raw_lng):
        return render_template("user/search.html", **context)

    try:
        service_id = int(raw_service)
    except ValueError:
        flash("Please choose a service.", "error")
        return render_template("user/search.html", **context), 400

    service = db.fetch_one(
        "SELECT id, name, icon FROM services WHERE id = %s AND is_active = 1",
        (service_id,),
    )
    if service is None:
        flash("That service is not available.", "error")
        return render_template("user/search.html", **context), 404

    try:
        lat, lng = parse_coordinates(raw_lat, raw_lng)
    except ValidationError as exc:
        flash(str(exc), "error")
        return render_template("user/search.html", **context), 400

    context.update(
        searched=True, selected_service=service, latitude=lat, longitude=lng
    )

    candidates = queries.search_providers(service_id)
    if not candidates:
        return render_template("user/search.html", **context)

    # One Dijkstra run from the customer answers every provider.
    finder = RouteFinder(lat, lng)
    reachable, unreachable = [], []
    for provider in candidates:
        provider["distance_km"] = finder.distance_to(
            float(provider["latitude"]), float(provider["longitude"])
        )
        (reachable if provider["distance_km"] is not None else unreachable).append(provider)

    # Scoring and ordering both live in the algorithm module, so the numbers
    # shown on each card are the same ones that decided the order.
    ranked = rank_providers(reachable, mode=mode, budget=budget)

    context.update(providers=ranked, unreachable=unreachable)
    return render_template("user/search.html", **context)


# How long a job may be booked for. The total charged is the provider's hourly
# rate multiplied by this, which is what makes the confirmation total real.
BOOKING_HOURS = (1, 2, 3, 4, 5, 6, 7, 8)


def read_booking_details(provider, source):
    """Validate every field a booking needs and work out the total.

    Used by both the confirmation step and the payment step, so the values that
    reach the database are always re-checked on the server - the hidden fields
    on the confirmation page are never trusted.
    """
    lat, lng = parse_coordinates(source.get("latitude"), source.get("longitude"))
    scheduled_date, scheduled_time = parse_schedule(
        source.get("scheduled_date"), source.get("scheduled_time")
    )
    address = clean_text(source.get("address"), "Job address", 200, min_length=3)
    note = clean_text(source.get("note"), "Note", 500, required=False)

    try:
        hours = int(source.get("estimated_hours") or 0)
    except (TypeError, ValueError):
        raise ValidationError("Please choose how long the job will take.")
    if hours not in BOOKING_HOURS:
        raise ValidationError("Please choose how long the job will take.")

    amount = round(float(provider["hourly_rate"]) * hours, 2)
    if amount < config.MINIMUM_PAYMENT_RUPEES:
        raise ValidationError(
            f"The total must be at least Rs {config.MINIMUM_PAYMENT_RUPEES}."
        )

    return {
        "latitude": lat,
        "longitude": lng,
        "scheduled_date": scheduled_date,
        "scheduled_time": scheduled_time,
        "address": address,
        "note": note,
        "estimated_hours": hours,
        "amount": amount,
    }


def slot_conflict(user_id, provider_id, scheduled_date, scheduled_time):
    """Return a message if this time slot cannot be booked, otherwise None."""
    duplicate = db.fetch_one(
        "SELECT id FROM bookings WHERE user_id = %s AND provider_id = %s "
        "AND scheduled_date = %s AND scheduled_time = %s "
        "AND status IN ('pending', 'accepted')",
        (user_id, provider_id, scheduled_date, scheduled_time),
    )
    if duplicate:
        return "You already have a booking with this provider at that time."

    taken = db.fetch_one(
        "SELECT id FROM bookings WHERE provider_id = %s "
        "AND scheduled_date = %s AND scheduled_time = %s "
        "AND status IN ('pending', 'accepted')",
        (provider_id, scheduled_date, scheduled_time),
    )
    if taken:
        return "This provider is already booked at that time. Please pick another slot."

    return None


@bp.route("/book/<int:provider_id>", methods=["GET", "POST"])
@auth.role_required("user")
def book(provider_id):
    """Show the Dijkstra route to one provider and take the booking."""
    provider = queries.get_provider(provider_id)
    if provider is None:
        flash("That provider no longer exists.", "error")
        return redirect(url_for("user.search"))

    if not (provider["is_approved"] and provider["is_available"] and provider["account_active"]):
        flash("That provider is not accepting bookings at the moment.", "error")
        return redirect(url_for("user.search"))

    source = request.form if request.method == "POST" else request.args
    try:
        lat, lng = parse_coordinates(source.get("latitude"), source.get("longitude"))
    except ValidationError as exc:
        flash(str(exc), "error")
        return redirect(url_for("user.search"))

    address = (source.get("address") or "").strip()

    finder = RouteFinder(lat, lng)
    route = finder.route_to(float(provider["latitude"]), float(provider["longitude"]))

    def show_form(status=200):
        return render_template(
            "user/book.html",
            provider=provider,
            route=route,
            latitude=lat,
            longitude=lng,
            address=address,
            form=source.to_dict(),
            galli_token=config.GALLI_ACCESS_TOKEN,
            reviews=queries.reviews_for_provider(provider_id, limit=5),
            # The provider's working days, both to show on the page and to
            # check against in the browser before the form is submitted.
            windows=queries.availability_windows(
                queries.availability_map([provider_id]).get(provider_id, {})
            ),
        ), status

    if request.method == "GET":
        return show_form()

    # ---- the form was submitted: check it, then show the confirmation ----
    # Nothing is written to the database yet. The booking is only created once
    # the customer confirms and starts the payment.
    try:
        details = read_booking_details(provider, request.form)
    except ValidationError as exc:
        flash(str(exc), "error")
        return show_form(400)

    conflict = slot_conflict(
        g.user["id"], provider_id, details["scheduled_date"], details["scheduled_time"]
    )
    if conflict:
        flash(conflict, "error")
        return show_form(409)

    return render_template(
        "user/confirm.html",
        provider=provider,
        route=route,
        details=details,
        khalti_ready=khalti.is_configured(),
    )


# ---------------------------------------------------------------------------
# Payment
# ---------------------------------------------------------------------------
def begin_khalti_payment(booking_id, payment_id, amount, provider_name, description=None):
    """Ask Khalti for a payment link for one booking and redirect to it.

    A fresh purchase_order_id is generated for every attempt, because Khalti
    will not reuse a `pidx` and neither will we.
    """
    order_id = f"SP-{booking_id}-{uuid4().hex[:8]}"

    # The provider's real business name from the database - never a hard-coded
    # shop name. It is sent as the product so that Khalti's payment page shows
    # it under "Product Summary".
    business_name = (provider_name or "").strip() or "Service Provider"

    try:
        pidx, payment_url = khalti.initiate(
            amount_rupees=amount,
            order_id=order_id,
            order_name=business_name,
            product_name=business_name,
            breakdown_label=description or f"Booking #{booking_id}",
            return_url=url_for("user.payment_callback", _external=True),
            website_url=url_for("index", _external=True),
            customer={
                "name": g.user["name"],
                "email": g.user["email"],
                "phone": g.user["phone"],
            },
        )
    except khalti.KhaltiError as exc:
        db.execute("UPDATE payments SET status = 'failed' WHERE id = %s", (payment_id,))
        flash(f"Could not start the payment: {exc}", "error")
        return redirect(url_for("user.bookings"))

    # Store the pidx so the callback can find this payment again.
    db.execute(
        "UPDATE payments SET pidx = %s, status = 'pending' WHERE id = %s",
        (pidx, payment_id),
    )
    return redirect(payment_url)


@bp.post("/book/<int:provider_id>/request")
@auth.role_required("user")
def submit_request(provider_id):
    """Create the booking. No money is involved at this point.

    The customer pays only after the provider has accepted, so no payment row
    is created here - see pay_booking().
    """
    provider = queries.get_provider(provider_id)
    if provider is None:
        flash("That provider no longer exists.", "error")
        return redirect(url_for("user.search"))
    if not (provider["is_approved"] and provider["is_available"] and provider["account_active"]):
        flash("That provider is not accepting bookings at the moment.", "error")
        return redirect(url_for("user.search"))

    def back_to_form():
        """Return to the booking page keeping the location already chosen."""
        return redirect(url_for(
            "user.book", provider_id=provider_id,
            latitude=request.form.get("latitude"),
            longitude=request.form.get("longitude"),
            address=request.form.get("address"),
        ))

    # Everything is validated again here - the confirmation page's hidden
    # fields are just a browser's copy and could have been edited.
    try:
        details = read_booking_details(provider, request.form)
    except ValidationError as exc:
        flash(str(exc), "error")
        return back_to_form()

    # Someone else may have taken the slot while this customer was confirming.
    conflict = slot_conflict(
        g.user["id"], provider_id, details["scheduled_date"], details["scheduled_time"]
    )
    if conflict:
        flash(conflict, "error")
        return back_to_form()

    # The provider must be working that weekday, the job must start inside
    # their hours, and it must finish inside them too.
    days = queries.availability_map([provider_id]).get(provider_id, {})
    problem = queries.check_booking_window(
        days, details["scheduled_date"], details["scheduled_time"],
        details["estimated_hours"],
    )
    if problem:
        flash(problem["reason"], "error")
        flash("This provider is available on: " + "; ".join(
            f"{w['name']} {w['label']}" for w in problem["windows"]), "info")
        return back_to_form()

    finder = RouteFinder(details["latitude"], details["longitude"])
    route = finder.route_to(float(provider["latitude"]), float(provider["longitude"]))

    try:
        booking_id = db.execute(
            "INSERT INTO bookings (user_id, provider_id, service_id, scheduled_date, "
            "scheduled_time, address, latitude, longitude, note, estimated_hours, "
            "distance_km, status) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'pending')",
            (
                g.user["id"], provider_id, provider["service_id"],
                details["scheduled_date"], details["scheduled_time"], details["address"],
                details["latitude"], details["longitude"], details["note"],
                details["estimated_hours"],
                route["total_km"] if route["found"] else None,
            ),
        )
    except db.DatabaseError as exc:
        # The database refuses two live bookings in the same slot. This only
        # fires when another customer booked it in the moment between the check
        # above and this insert.
        if "uq_bookings_active_slot" in str(exc):
            flash("Someone just took that time slot. Please choose another one.", "error")
            return back_to_form()
        raise

    # Tell the provider there is something waiting for them.
    owner_id = queries.provider_owner_id(provider_id)
    if owner_id:
        queries.add_notification(
            owner_id,
            f"New request #{booking_id} from {g.user['name']} for "
            f"{details['scheduled_date']:%d %b} at {details['scheduled_time']:%H:%M}.",
            booking_id,
        )

    flash(
        f"Request #{booking_id} sent to {provider['business_name']}. "
        "You will be able to pay once they accept it.",
        "success",
    )
    return redirect(url_for("user.bookings"))


@bp.post("/bookings/<int:booking_id>/pay")
@auth.role_required("user")
def pay_booking(booking_id):
    """Pay for a booking the provider has accepted.

    This is the only place a payment row is created. Paying is refused until
    the provider has accepted, which is exactly what the customer is told when
    the request is submitted.
    """
    booking = db.fetch_one(
        "SELECT b.id, b.status, b.estimated_hours, p.business_name, p.hourly_rate, "
        "s.name AS service_name, "
        "pay.id AS payment_id, pay.amount, pay.status AS payment_status "
        "FROM bookings b "
        "JOIN providers p ON p.id = b.provider_id "
        "JOIN services s  ON s.id = b.service_id "
        "LEFT JOIN payments pay ON pay.booking_id = b.id "
        "WHERE b.id = %s AND b.user_id = %s",
        (booking_id, g.user["id"]),
    )
    if booking is None:
        flash("Booking not found.", "error")
        return redirect(url_for("user.bookings"))

    if booking["payment_status"] == "paid":
        flash("This booking has already been paid for.", "error")
        return redirect(url_for("user.bookings"))

    if booking["status"] != "accepted":
        if booking["status"] == "pending":
            flash("The provider has not accepted this request yet, so there is "
                  "nothing to pay for.", "error")
        else:
            flash(f"A {booking['status']} booking cannot be paid for.", "error")
        return redirect(url_for("user.bookings"))

    if not khalti.is_configured():
        flash("Online payment is not configured. Please contact the administrator.", "error")
        return redirect(url_for("user.bookings"))

    # The amount is worked out from the booking, never from the browser.
    amount = round(float(booking["hourly_rate"]) * int(booking["estimated_hours"]), 2)

    payment_id = booking["payment_id"]
    if payment_id is None:
        payment_id = db.execute(
            "INSERT INTO payments (booking_id, user_id, amount, payment_method, status) "
            "VALUES (%s, %s, %s, 'khalti', 'pending')",
            (booking_id, g.user["id"], amount),
        )
    else:
        # An earlier attempt failed or was abandoned - reuse the row.
        db.execute(
            "UPDATE payments SET amount = %s, status = 'pending' WHERE id = %s",
            (amount, payment_id),
        )

    return begin_khalti_payment(
        booking_id, payment_id, amount, booking["business_name"],
        description=(
            f"{booking['service_name']} - {booking['estimated_hours']} hr "
            f"at Rs {float(booking['hourly_rate']):.0f}/hr"
        ),
    )


@bp.get("/payment/callback")
@auth.role_required("user")
def payment_callback():
    """Where Khalti sends the customer back to.

    The query string Khalti adds (including status=Completed) is only a hint -
    anybody could type it. The payment is confirmed by asking Khalti directly
    with the lookup API, and nothing else is allowed to mark it paid.
    """
    pidx = (request.args.get("pidx") or "").strip()
    if not pidx:
        flash("The payment was not completed.", "error")
        return redirect(url_for("user.bookings"))

    payment = db.fetch_one(
        "SELECT id, booking_id, user_id, amount, status FROM payments WHERE pidx = %s",
        (pidx,),
    )
    # Also checks the payment belongs to whoever is logged in, so one customer
    # cannot confirm another customer's payment.
    if payment is None or payment["user_id"] != g.user["id"]:
        flash("That payment does not belong to your account.", "error")
        return redirect(url_for("user.bookings"))

    if payment["status"] == "paid":
        # Coming back a second time (a refresh, or the back button) shows the
        # receipt again rather than dumping them on the booking list.
        flash("This booking has already been paid for.", "info")
        return redirect(url_for("user.receipt", booking_id=payment["booking_id"]))

    try:
        result = khalti.lookup(pidx)
    except khalti.KhaltiError as exc:
        # Left pending on purpose: an unverified payment must never be treated
        # as either paid or failed.
        flash(f"Could not confirm the payment yet: {exc}", "error")
        return redirect(url_for("user.bookings"))

    if result["status"] != khalti.STATUS_COMPLETED:
        if result["status"] in ("User canceled", "Expired"):
            db.execute(
                "UPDATE payments SET status = 'failed' WHERE id = %s AND status = 'pending'",
                (payment["id"],),
            )
        flash(f"The payment was not completed (Khalti says: {result['status']}).", "error")
        return redirect(url_for("user.bookings"))

    # Khalti says Completed - now make sure it paid the right amount.
    if result["total_amount"] != khalti.rupees_to_paisa(payment["amount"]):
        db.execute("UPDATE payments SET status = 'failed' WHERE id = %s", (payment["id"],))
        flash(
            "The amount Khalti confirmed does not match this booking. "
            "Please contact the administrator.",
            "error",
        )
        return redirect(url_for("user.bookings"))

    # "AND status <> 'paid'" makes a repeated callback harmless.
    db.execute(
        "UPDATE payments SET status = 'paid', transaction_id = %s, paid_at = NOW() "
        "WHERE id = %s AND status <> 'paid'",
        (result["transaction_id"], payment["id"]),
    )
    owner = db.fetch_one(
        "SELECT p.user_id FROM bookings b JOIN providers p ON p.id = b.provider_id "
        "WHERE b.id = %s",
        (payment["booking_id"],),
    )
    if owner:
        queries.add_notification(
            owner["user_id"],
            f"{g.user['name']} paid Rs {float(payment['amount']):.0f} for "
            f"booking #{payment['booking_id']}. You can now do the job.",
            payment["booking_id"],
        )

    flash(
        f"Payment received for booking #{payment['booking_id']}. "
        "The provider has been told and can now go ahead.",
        "success",
    )
    # Straight to the receipt, which is the proof of payment the customer
    # wants at this moment. It carries a button back to their bookings.
    return redirect(url_for("user.receipt", booking_id=payment["booking_id"]))


@bp.route("/bookings")
@auth.role_required("user")
def bookings():
    """This customer's bookings, searchable by provider or shop name."""
    search = (request.args.get("q") or "").strip()
    sort = queries.resolve_booking_sort(request.args.get("sort"))
    status = (request.args.get("status") or "").strip().lower()
    valid_statuses = {"pending", "accepted", "rejected", "completed", "cancelled"}
    if status not in valid_statuses:
        status = ""

    rows = queries.bookings_for_user(
        g.user["id"], search=search, sort=sort, status=status
    )
    count_rows = db.fetch_all(
        "SELECT status, COUNT(*) AS total FROM bookings "
        "WHERE user_id = %s GROUP BY status",
        (g.user["id"],),
    )
    status_counts = {name: 0 for name in valid_statuses}
    for row in count_rows:
        if row["status"] in status_counts:
            status_counts[row["status"]] = row["total"]

    return render_template(
        "user/bookings.html",
        bookings=rows,
        search=search,
        sort=sort,
        status=status,
        status_counts=status_counts,
        total_bookings=sum(status_counts.values()),
        sorts=queries.BOOKING_SORTS,
        # Only providers this customer has completed a job with may be
        # favourited, so the heart is only offered on those.
        usable=queries.providers_used_by(g.user["id"]),
        favourites=queries.favourite_ids(g.user["id"]),
    )


@bp.post("/favourites/<int:provider_id>/toggle")
@auth.role_required("user")
def toggle_favourite(provider_id):
    """Add or remove a favourite.

    Refused unless this customer has actually completed a job with the
    provider, and the row is always keyed to the logged in account so nobody
    can change somebody else's favourites.
    """
    provider = queries.get_provider(provider_id)
    if provider is None:
        flash("That provider no longer exists.", "error")
        return redirect(request.referrer or url_for("user.bookings"))

    if queries.is_favourite(g.user["id"], provider_id):
        db.execute(
            "DELETE FROM favourite_providers WHERE user_id = %s AND provider_id = %s",
            (g.user["id"], provider_id),
        )
        flash(f"{provider['business_name']} removed from your favourites.", "success")
    else:
        if not queries.has_completed_booking(g.user["id"], provider_id):
            flash(
                "You can only add a provider to your favourites after they have "
                "completed a job for you.",
                "error",
            )
            return redirect(request.referrer or url_for("user.bookings"))

        # The UNIQUE key means a double submit cannot create a second row.
        db.execute(
            "INSERT IGNORE INTO favourite_providers (user_id, provider_id) "
            "VALUES (%s, %s)",
            (g.user["id"], provider_id),
        )
        flash(f"{provider['business_name']} added to your favourites.", "success")

    return redirect(request.referrer or url_for("user.bookings"))


@bp.route("/favourites")
@auth.role_required("user")
def favourites():
    """The customer's own saved providers."""
    return render_template(
        "user/favourites.html",
        providers=queries.favourites_for(g.user["id"]),
    )


@bp.post("/bookings/<int:booking_id>/reschedule")
@auth.role_required("user")
def reschedule_booking(booking_id):
    """Move a request to a different date and time.

    Only while the provider has not answered yet: once they have accepted, the
    time they agreed to must not change underneath them.
    """
    booking = db.fetch_one(
        "SELECT b.id, b.status, b.provider_id, b.estimated_hours, p.business_name "
        "FROM bookings b JOIN providers p ON p.id = b.provider_id "
        "WHERE b.id = %s AND b.user_id = %s",
        (booking_id, g.user["id"]),
    )
    if booking is None:
        flash("Booking not found.", "error")
        return redirect(url_for("user.bookings"))

    if booking["status"] != "pending":
        flash(
            f"A {booking['status']} booking cannot be rescheduled. "
            "Cancel it and send a new request instead.",
            "error",
        )
        return redirect(url_for("user.bookings"))

    try:
        new_date, new_time = parse_schedule(
            request.form.get("scheduled_date"), request.form.get("scheduled_time")
        )
    except ValidationError as exc:
        flash(str(exc), "error")
        return redirect(url_for("user.bookings"))

    days = queries.availability_map([booking["provider_id"]]).get(booking["provider_id"], {})
    problem = queries.check_booking_window(
        days, new_date, new_time, booking["estimated_hours"]
    )
    if problem:
        flash(problem["reason"], "error")
        flash("This provider is available on: " + "; ".join(
            f"{w['name']} {w['label']}" for w in problem["windows"]), "info")
        return redirect(url_for("user.bookings"))

    conflict = slot_conflict(g.user["id"], booking["provider_id"], new_date, new_time)
    if conflict:
        flash(conflict, "error")
        return redirect(url_for("user.bookings"))

    try:
        db.execute(
            "UPDATE bookings SET scheduled_date = %s, scheduled_time = %s "
            "WHERE id = %s AND status = 'pending'",
            (new_date, new_time, booking_id),
        )
    except db.DatabaseError as exc:
        if "uq_bookings_active_slot" in str(exc):
            flash("Someone just took that time slot. Please choose another one.", "error")
            return redirect(url_for("user.bookings"))
        raise

    owner_id = queries.provider_owner_id(booking["provider_id"])
    if owner_id:
        queries.add_notification(
            owner_id,
            f"{g.user['name']} moved request #{booking_id} to "
            f"{new_date:%d %b} at {new_time:%H:%M}.",
            booking_id,
        )

    flash(
        f"Booking #{booking_id} moved to {new_date:%d %b %Y} at {new_time:%H:%M}.",
        "success",
    )
    return redirect(url_for("user.bookings"))


@bp.route("/notifications")
@auth.login_required
def notifications():
    """Everything this account has been told, newest first.

    Opening the page marks them read, which is what clears the nav badge.
    """
    items = queries.notifications_for(g.user["id"])
    db.execute(
        "UPDATE notifications SET is_read = 1 WHERE user_id = %s AND is_read = 0",
        (g.user["id"],),
    )
    return render_template("notifications.html", notifications=items)


@bp.route("/bookings/<int:booking_id>/receipt")
@auth.role_required("user")
def receipt(booking_id):
    """A printable receipt for a booking that has been paid for."""
    booking = queries.get_booking(booking_id)
    if booking is None or booking["user_id"] != g.user["id"]:
        flash("Booking not found.", "error")
        return redirect(url_for("user.bookings"))

    if booking["payment_status"] != "paid":
        flash("A receipt is only available once the payment has gone through.", "error")
        return redirect(url_for("user.bookings"))

    return render_template("user/receipt.html", booking=booking)


@bp.post("/bookings/<int:booking_id>/cancel")
@auth.role_required("user")
def cancel_booking(booking_id):
    booking = db.fetch_one(
        "SELECT b.id, b.status, b.provider_id, s.name AS service_name, "
        "p.business_name "
        "FROM bookings b "
        "JOIN services s  ON s.id = b.service_id "
        "JOIN providers p ON p.id = b.provider_id "
        "WHERE b.id = %s AND b.user_id = %s",
        (booking_id, g.user["id"]),
    )
    if booking is None:
        flash("Booking not found.", "error")
        return redirect(url_for("user.bookings"))

    # Only a job that has not happened yet can be cancelled.
    if booking["status"] not in ("pending", "accepted"):
        flash(f"A {booking['status']} booking cannot be cancelled.", "error")
        return redirect(url_for("user.bookings"))

    # Why they are cancelling, chosen in the box that appears when they press
    # Cancel. It is optional, so a cancellation still works with JavaScript
    # switched off, and it is stored rather than only shown in a message.
    try:
        reason = clean_text(request.form.get("reason"), "Reason", 200,
                            required=False)
    except ValidationError:
        reason = ""

    db.execute(
        "UPDATE bookings SET status = 'cancelled', cancel_reason = %s WHERE id = %s",
        (reason, booking_id),
    )

    # Cancelling a booking that was already paid for records a refund, so the
    # payment status never disagrees with the booking status.
    refunded = db.execute(
        "UPDATE payments SET status = 'refunded', refunded_at = NOW() "
        "WHERE booking_id = %s AND status = 'paid'",
        (booking_id,),
    )

    because = f" Reason: {reason}" if reason else ""
    owner_id = queries.provider_owner_id(booking["provider_id"])
    if owner_id:
        queries.add_notification(
            owner_id,
            f"{g.user['name']} cancelled booking #{booking_id}.{because}",
            booking_id,
            "Booking Cancelled",
        )

    queries.notify_admins(
        "Booking Cancelled",
        f"Booking #{booking_id} for {booking['service_name']} with "
        f"{booking['business_name']} was cancelled by {g.user['name']}."
        f"{because}",
        booking_id,
    )

    if refunded:
        amount = db.fetch_one(
            "SELECT amount FROM payments WHERE booking_id = %s", (booking_id,)
        )
        queries.notify_admins(
            "Payment Refunded",
            f"Rs. {float(amount['amount']):.0f} was refunded to "
            f"{g.user['name']} for booking #{booking_id}.",
            booking_id,
        )
        flash("Booking cancelled and the payment marked for refund.", "success")
    else:
        flash("Booking cancelled.", "success")
    return redirect(url_for("user.bookings"))


@bp.post("/bookings/<int:booking_id>/review")
@auth.role_required("user")
def review_booking(booking_id):
    booking = db.fetch_one(
        "SELECT id, provider_id, status FROM bookings WHERE id = %s AND user_id = %s",
        (booking_id, g.user["id"]),
    )
    if booking is None:
        flash("Booking not found.", "error")
        return redirect(url_for("user.bookings"))

    if booking["status"] != "completed":
        flash("You can only review a service after it has been completed.", "error")
        return redirect(url_for("user.bookings"))

    if db.fetch_one("SELECT id FROM reviews WHERE booking_id = %s", (booking_id,)):
        flash("You have already reviewed this booking.", "error")
        return redirect(url_for("user.bookings"))

    try:
        rating = parse_rating(request.form.get("rating"))
        comment = clean_text(request.form.get("comment"), "Comment", 500, required=False)
    except ValidationError as exc:
        flash(str(exc), "error")
        return redirect(url_for("user.bookings"))

    db.execute(
        "INSERT INTO reviews (booking_id, user_id, provider_id, rating, comment) "
        "VALUES (%s, %s, %s, %s, %s)",
        (booking_id, g.user["id"], booking["provider_id"], rating, comment),
    )
    flash("Thank you for your review.", "success")
    return redirect(url_for("user.bookings"))


@bp.route("/profile", methods=["GET", "POST"])
@auth.login_required
def profile():
    """Shared by every role - name and phone are on the users table."""
    if request.method == "POST":
        try:
            name = clean_text(request.form.get("name"), "Name", 80, min_length=3)
            phone = parse_phone(request.form.get("phone"))
        except ValidationError as exc:
            flash(str(exc), "error")
            return redirect(url_for("user.profile"))

        db.execute(
            "UPDATE users SET name = %s, phone = %s WHERE id = %s",
            (name, phone, g.user["id"]),
        )
        flash("Profile updated.", "success")
        return redirect(url_for("user.profile"))

    return render_template("user/profile.html")


@bp.post("/profile/password")
@auth.login_required
def change_password():
    """Change the signed-in account's own password.

    Shared by customers, providers and administrators: the account is always
    taken from the session, so nobody can change anyone else's password.
    """
    current = request.form.get("current_password") or ""
    new_password = request.form.get("new_password") or ""
    confirm = request.form.get("confirm_password") or ""

    row = db.fetch_one(
        "SELECT password_hash, auth_version FROM users WHERE id = %s",
        (g.user["id"],),
    )
    if row is None or not auth.verify_password(row["password_hash"], current):
        flash("Your current password is not correct.", "error")
        return redirect(url_for("user.profile"))

    # The same rules the registration form uses, so the policy is in one place.
    errors = auth.validate_password(new_password, confirm)
    if new_password == current:
        errors.append("The new password must be different from the current one.")
    if errors:
        for message in errors:
            flash(message, "error")
        return redirect(url_for("user.profile"))

    db.execute(
        "UPDATE users SET password_hash = %s, auth_version = auth_version + 1 "
        "WHERE id = %s",
        (auth.hash_password(new_password), g.user["id"]),
    )
    # A password change proves the account owner is present, so any recovery
    # links requested earlier should stop working immediately.
    db.execute(
        "UPDATE password_reset_tokens SET used_at = UTC_TIMESTAMP() "
        "WHERE user_id = %s AND used_at IS NULL",
        (g.user["id"],),
    )
    # Keep this browser signed in at the new version; every other session still
    # carries the old value and will be rejected on its next request.
    session["auth_version"] = row["auth_version"] + 1
    flash("Your password has been changed.", "success")
    return redirect(url_for("user.profile"))


@bp.get("/api/route")
@auth.login_required
def road_route():
    """Real driving route between two points, from Galli's routing engine.

    The browser asks Flask and Flask asks Galli, so the access token stays on
    the server. The geometry returned is the actual road path - if the routing
    engine cannot produce one, this reports a failure rather than inventing a
    straight line between the two points.
    """
    try:
        src_lat, src_lng = parse_coordinates(
            request.args.get("srcLat"), request.args.get("srcLng")
        )
        dst_lat, dst_lng = parse_coordinates(
            request.args.get("dstLat"), request.args.get("dstLng")
        )
    except ValidationError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400

    # Two points at the same place have no route between them, which is a real
    # answer rather than a failure - it happens whenever the job address is the
    # provider's own address.
    if haversine_km(src_lat, src_lng, dst_lat, dst_lng) < 0.05:
        return jsonify({
            "ok": True,
            "same_location": True,
            "distance_km": 0.0,
            "duration_min": 0,
            "points": [[src_lat, src_lng], [dst_lat, dst_lng]],
        })

    if not config.GALLI_ACCESS_TOKEN:
        return jsonify({"ok": False, "error": "Map service is not configured."}), 503

    try:
        response = requests.get(
            "https://route-init.gallimap.com/api/v1/routing",
            params={
                "accessToken": config.GALLI_ACCESS_TOKEN,
                "mode": "driving",
                "srcLat": src_lat, "srcLng": src_lng,
                "dstLat": dst_lat, "dstLng": dst_lng,
            },
            timeout=12,
        )
        response.raise_for_status()
        payload = response.json()
    except (requests.RequestException, ValueError):
        return jsonify({"ok": False, "error": "The routing service is unavailable."}), 502

    if not payload.get("success"):
        return jsonify({"ok": False, "error": "The routing service refused the request."}), 502

    routes = (payload.get("data") or {}).get("data") or []
    if not routes:
        return jsonify({"ok": False, "error": "No road route was found."}), 404

    route = routes[0]
    # Galli returns [longitude, latitude] pairs.
    latlngs = route.get("latlngs") or []
    distance_m = float(route.get("distance") or 0)

    # A zero distance, or a handful of identical points, means the engine could
    # not route between these locations - it is not a usable route.
    unique_points = {tuple(p) for p in latlngs}
    if distance_m <= 0 or len(unique_points) < 3:
        return jsonify({"ok": False, "error": "No road route was found between these locations."}), 404

    return jsonify({
        "ok": True,
        "distance_km": round(distance_m / 1000, 2),
        "duration_min": int(round(float(route.get("duration") or 0) / 60)),
        # Sent as [lat, lng] so the browser does not have to flip them.
        "points": [[p[1], p[0]] for p in latlngs],
    })


@bp.get("/api/reverse-geocode")
@auth.login_required
def reverse_geocode():
    """Turn the clicked coordinates into a readable address.

    The browser asks Flask, and Flask asks Galli Maps, so the access token is
    never put into a URL the browser can be seen fetching.
    """
    try:
        lat, lng = parse_coordinates(
            request.args.get("lat"), request.args.get("lng")
        )
    except ValidationError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400

    if not config.GALLI_ACCESS_TOKEN:
        return jsonify({"ok": False, "error": "Map service is not configured."}), 503

    try:
        response = requests.get(
            "https://route-init.gallimap.com/api/v1/reverse/generalReverse",
            params={
                "accessToken": config.GALLI_ACCESS_TOKEN,
                "lat": lat,
                "lng": lng,
            },
            timeout=8,
        )
        response.raise_for_status()
        data = response.json()
    except (requests.RequestException, ValueError):
        # The map still works without a name, so this is not a hard failure.
        return jsonify({"ok": False, "error": "Could not look up that address."}), 502

    place = (data.get("data") or {}) if data.get("success") else {}
    name = place.get("generalName") or place.get("place") or ""
    return jsonify({"ok": True, "address": name})
