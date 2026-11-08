"""The provider workspace: incoming jobs, profile and availability."""

from flask import Blueprint, flash, g, redirect, render_template, request, url_for

import auth
import config
import db
import queries
from validators import (
    ValidationError, as_clock, clean_text, parse_clock, parse_coordinates,
    parse_positive_number,
)

bp = Blueprint("provider", __name__, url_prefix="/provider")

BOOKING_STATUSES = ("pending", "accepted", "rejected", "completed", "cancelled")

# What a provider is allowed to do to a booking, and what state it moves to.
# Anything not listed here is rejected, so a booking can never jump from
# "completed" back to "pending" or be accepted twice.
ALLOWED_TRANSITIONS = {
    "accept": ("pending", "accepted",
               "Booking accepted. The customer can now pay for it."),
    "reject": ("pending", "rejected", "Booking rejected."),
    "complete": ("accepted", "completed", "Job marked as completed."),
}


def _describe_week(rows):
    """The working week as one short line, for a notification message.

    Days that share the same hours are grouped, so a provider who works the
    same times all week reads as "every day 09:00 AM - 05:00 PM" rather than
    as seven separate entries.
    """
    def shown(value):
        return queries._clock(queries._as_minutes(value))

    if not rows:
        return "06:00 AM - 08:00 PM every day"

    by_hours = {}
    for row in rows:
        hours = f"{shown(row['start_time'])} - {shown(row['end_time'])}"
        by_hours.setdefault(hours, []).append(queries.WEEKDAYS[row["weekday"]][:3])

    if len(by_hours) == 1 and len(rows) == 7:
        return f"{next(iter(by_hours))} every day"
    return "; ".join(f"{', '.join(days)} {hours}" for hours, days in by_hours.items())


def _my_profile():
    """The provider row belonging to the logged in account, or None."""
    return queries.get_provider_by_user(g.user["id"])


@bp.route("/dashboard")
@auth.role_required("provider")
def dashboard():
    profile = _my_profile()
    if profile is None:
        flash("Your provider profile is missing. Please contact the administrator.", "error")
        return render_template("provider/dashboard.html", profile=None,
                               bookings=[], stats={}, reviews=[])

    bookings = queries.bookings_for_provider(profile["id"])

    stats = {
        "pending": sum(1 for b in bookings if b["status"] == "pending"),
        "accepted": sum(1 for b in bookings if b["status"] == "accepted"),
        "completed": sum(1 for b in bookings if b["status"] == "completed"),
        "total": len(bookings),
    }

    return render_template(
        "provider/dashboard.html",
        profile=profile,
        bookings=bookings,
        stats=stats,
        reviews=queries.reviews_for_provider(profile["id"]),
    )


@bp.route("/bookings")
@auth.role_required("provider")
def bookings():
    """The provider's own bookings, optionally filtered by status.

    The dashboard's statistic cards link here, so the filter has to be applied
    on the server rather than by hiding rows in the browser.
    """
    profile = _my_profile()
    if profile is None:
        flash("Your provider profile is missing.", "error")
        return redirect(url_for("provider.dashboard"))

    status = request.args.get("status", "")
    if status not in BOOKING_STATUSES:
        status = ""
    search = (request.args.get("q") or "").strip()

    # Always scoped to this provider's own id, so a search can never reach
    # another provider's bookings.
    all_bookings = queries.bookings_for_provider(profile["id"])
    matched = queries.bookings_for_provider(profile["id"], search=search)
    shown = [b for b in matched if not status or b["status"] == status]

    # Counts for the badges on the filter bar. They are taken from the searched
    # set, not from every booking, so each number is exactly how many rows that
    # tab will show if it is clicked.
    counts = {"": len(matched)}
    for name in BOOKING_STATUSES:
        counts[name] = sum(1 for b in matched if b["status"] == name)

    return render_template(
        "provider/bookings.html",
        profile=profile,
        bookings=shown,
        statuses=BOOKING_STATUSES,
        active_status=status,
        search=search,
        counts=counts,
        total=len(all_bookings),
    )


@bp.route("/reviews")
@auth.role_required("provider")
def reviews():
    profile = _my_profile()
    if profile is None:
        flash("Your provider profile is missing.", "error")
        return redirect(url_for("provider.dashboard"))

    rating, sort = queries.read_review_filters(request.args)

    # profile["id"] comes from the signed-in account, never from the URL, so a
    # provider can only ever be shown their own reviews however the rating and
    # sort parameters are changed.
    return render_template(
        "provider/reviews.html",
        profile=profile,
        reviews=queries.reviews_for_provider(
            profile["id"], limit=100, rating=rating, sort=sort
        ),
        summary=queries.rating_breakdown(profile["id"]),
        sorts=queries.REVIEW_SORTS,
        active_rating=rating,
        active_sort=sort,
    )


@bp.route("/bookings/<int:booking_id>")
@auth.role_required("provider")
def booking_detail(booking_id):
    """One of this provider's own jobs, with the road route to the address."""
    profile = _my_profile()
    if profile is None:
        flash("Your provider profile is missing.", "error")
        return redirect(url_for("provider.dashboard"))

    booking = queries.get_booking(booking_id)
    # Checking the provider id here is what stops one provider opening
    # another provider's job by guessing the number in the URL.
    if booking is None or booking["provider_id"] != profile["id"]:
        flash("Booking not found.", "error")
        return redirect(url_for("provider.bookings"))

    return render_template(
        "provider/booking_detail.html",
        profile=profile,
        booking=booking,
        galli_token=config.GALLI_ACCESS_TOKEN,
    )


@bp.post("/bookings/<int:booking_id>/<action>")
@auth.role_required("provider")
def update_booking(booking_id, action):
    if action not in ALLOWED_TRANSITIONS:
        flash("Unknown action.", "error")
        return redirect(url_for("provider.dashboard"))

    profile = _my_profile()
    if profile is None:
        flash("Your provider profile is missing.", "error")
        return redirect(url_for("provider.dashboard"))

    # Matching on provider_id as well as booking id means one provider can
    # never change another provider's booking by guessing an id.
    booking = db.fetch_one(
        "SELECT b.id, b.status, b.user_id AS customer_id, pay.status AS payment_status "
        "FROM bookings b LEFT JOIN payments pay ON pay.booking_id = b.id "
        "WHERE b.id = %s AND b.provider_id = %s",
        (booking_id, profile["id"]),
    )
    if booking is None:
        flash("Booking not found.", "error")
        return redirect(url_for("provider.dashboard"))

    required_status, new_status, message = ALLOWED_TRANSITIONS[action]
    if booking["status"] != required_status:
        flash(
            f"A booking that is already {booking['status']} cannot be "
            f"{'accepted' if action == 'accept' else action + 'ed'}.",
            "error",
        )
        return redirect(url_for("provider.dashboard"))

    # The customer pays only after the job is accepted, so accepting an unpaid
    # request is the normal case. The job cannot be finished until they have
    # paid, which is what the customer was told when they sent the request.
    if action == "complete" and booking["payment_status"] != "paid":
        flash("The customer has not paid for this job yet, so it cannot be "
              "marked as completed.", "error")
        return redirect(url_for("provider.dashboard"))

    db.execute(
        "UPDATE bookings SET status = %s WHERE id = %s", (new_status, booking_id)
    )

    # Tell the customer what happened, with the next step where there is one.
    told = {
        "accept": f"{profile['business_name']} accepted booking #{booking_id}. "
                  "You can now pay for it.",
        "reject": f"{profile['business_name']} could not take booking #{booking_id}. "
                  "You have not been charged.",
        "complete": f"{profile['business_name']} marked booking #{booking_id} "
                    "as completed. You can now leave a review.",
    }[action]
    queries.add_notification(booking["customer_id"], told, booking_id)

    # Rejecting normally involves no money at all, because the customer has not
    # paid yet. This only matters if they paid and the provider then rejected.
    if action == "reject":
        refunded = db.execute(
            "UPDATE payments SET status = 'refunded', refunded_at = NOW() "
            "WHERE booking_id = %s AND status = 'paid'",
            (booking_id,),
        )
        if refunded:
            message = "Booking rejected and the payment marked for refund."
            paid = db.fetch_one(
                "SELECT pay.amount, cu.name AS customer_name "
                "FROM payments pay JOIN bookings b ON b.id = pay.booking_id "
                "JOIN users cu ON cu.id = b.user_id WHERE pay.booking_id = %s",
                (booking_id,),
            )
            if paid:
                queries.notify_admins(
                    "Payment Refunded",
                    f"Rs. {float(paid['amount']):.0f} was refunded to "
                    f"{paid['customer_name']} for booking #{booking_id} after "
                    f"{profile['business_name']} rejected it.",
                    booking_id,
                )

    flash(message, "success")
    return redirect(url_for("provider.dashboard"))


@bp.route("/availability", methods=["GET", "POST"])
@auth.role_required("provider")
def availability():
    """The days and hours this provider works.

    Stating nothing means "available every day, 06:00 to 20:00", so a provider
    who never opens this page keeps behaving exactly as before.
    """
    profile = _my_profile()
    if profile is None:
        flash("Your provider profile is missing.", "error")
        return redirect(url_for("provider.dashboard"))

    if request.method == "POST":
        rows, errors = [], []
        for weekday in range(7):
            if not request.form.get(f"work_{weekday}"):
                continue            # a day left unticked is a day off
            try:
                start = parse_clock(request.form.get(f"start_{weekday}"), "Start time")
                end = parse_clock(request.form.get(f"end_{weekday}"), "End time")
            except ValidationError as exc:
                errors.append(f"{queries.WEEKDAYS[weekday]}: {exc}")
                continue
            if end <= start:
                errors.append(
                    f"{queries.WEEKDAYS[weekday]}: the end time must be after the start."
                )
                continue
            rows.append((weekday, start, end))

        if errors:
            for message in errors:
                flash(message, "error")
            return redirect(url_for("provider.availability"))

        # What the week looked like before, so the administrator can be told
        # what actually changed instead of just "something was saved".
        was = _describe_week(queries.availability_for(profile["id"]))

        # Replace the whole week in one go - simpler to follow than working out
        # which individual days changed.
        db.execute("DELETE FROM provider_availability WHERE provider_id = %s",
                   (profile["id"],))
        for weekday, start, end in rows:
            db.execute(
                "INSERT INTO provider_availability (provider_id, weekday, start_time, end_time) "
                "VALUES (%s, %s, %s, %s)",
                (profile["id"], weekday, start, end),
            )

        now = _describe_week(queries.availability_for(profile["id"]))
        if now != was:
            queries.notify_admins(
                "Service Availability Updated",
                f"{profile['business_name']} changed their available service "
                f"time from {was} to {now}.",
            )

        if rows:
            flash(f"Working hours saved for {len(rows)} day"
                  f"{'s' if len(rows) != 1 else ''}.", "success")
        else:
            flash("No working days set, so you are treated as available "
                  "every day from 06:00 to 20:00.", "success")
        return redirect(url_for("provider.availability"))

    # Turn the stored rows into one entry per weekday for the form.
    stored = {row["weekday"]: row for row in queries.availability_for(profile["id"])}
    week = []
    for weekday in range(7):
        row = stored.get(weekday)
        week.append({
            "weekday": weekday,
            "name": queries.WEEKDAYS[weekday],
            "works": row is not None,
            "start": as_clock(row["start_time"]) if row else queries.DEFAULT_START,
            "end": as_clock(row["end_time"]) if row else queries.DEFAULT_END,
        })

    return render_template(
        "provider/availability.html",
        profile=profile,
        week=week,
        using_default=not stored,
    )


def _tell_admin_what_changed(before, after, services):
    """Notify the administrator, but only about the changes that matter.

    A provider moving shop, switching to a different service, or closing their
    books are all things the administrator has to know about. A new bio, a
    changed price or a corrected phone number are not, so those are saved
    silently - otherwise the alerts page would be full of noise.
    """
    name = after["business_name"]

    if after["address"] != before["address"]:
        queries.notify_admins(
            "Provider Location Updated",
            f"{name} changed their business location from "
            f"{before['address']} to {after['address']}.",
        )

    if after["service_id"] != before["service_id"]:
        names = {s["id"]: s["name"] for s in services}
        queries.notify_admins(
            "Provider Service Changed",
            f"{name} changed their service from "
            f"{names.get(before['service_id'], 'an old service')} to "
            f"{names.get(after['service_id'], 'another service')}.",
        )

    if after["is_available"] != before["is_available"]:
        state = "is accepting work again" if after["is_available"]             else "has stopped accepting new work"
        queries.notify_admins("Provider Availability Changed", f"{name} {state}.")


@bp.route("/profile", methods=["GET", "POST"])
@auth.role_required("provider")
def profile():
    current = _my_profile()
    if current is None:
        flash("Your provider profile is missing. Please contact the administrator.", "error")
        return redirect(url_for("provider.dashboard"))

    services = queries.active_services()

    if request.method == "POST":
        try:
            service_id = int(request.form.get("service_id"))
            if service_id not in {s["id"] for s in services}:
                raise ValidationError("Please choose a valid service.")

            lat, lng = parse_coordinates(
                request.form.get("latitude"), request.form.get("longitude")
            )
            business_name = clean_text(
                request.form.get("business_name"), "Business name", 100, min_length=3
            )
            bio = clean_text(request.form.get("bio"), "About you", 500, required=False)
            address = clean_text(
                request.form.get("address"), "Work address", 150, min_length=3
            )
            hourly_rate = parse_positive_number(
                request.form.get("hourly_rate"), "Hourly rate", 100000
            )
            experience = int(
                parse_positive_number(request.form.get("experience_years"), "Experience", 60)
            )
        except (TypeError, ValueError):
            flash("Please choose the service you provide.", "error")
            return redirect(url_for("provider.profile"))
        except ValidationError as exc:
            flash(str(exc), "error")
            return redirect(url_for("provider.profile"))

        # A checkbox is simply absent when it is unticked.
        is_available = 1 if request.form.get("is_available") else 0

        db.execute(
            "UPDATE providers SET service_id = %s, business_name = %s, bio = %s, "
            "hourly_rate = %s, experience_years = %s, address = %s, "
            "latitude = %s, longitude = %s, is_available = %s WHERE id = %s",
            (
                service_id, business_name, bio, hourly_rate, experience,
                address, lat, lng, is_available, current["id"],
            ),
        )

        _tell_admin_what_changed(current, {
            "business_name": business_name,
            "service_id": service_id,
            "address": address,
            "is_available": is_available,
        }, services)

        flash("Profile updated.", "success")
        return redirect(url_for("provider.profile"))

    return render_template(
        "provider/profile.html",
        profile=current,
        services=services,
        galli_token=config.GALLI_ACCESS_TOKEN,
    )
