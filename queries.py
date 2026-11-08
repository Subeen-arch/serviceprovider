"""SQL that more than one route needs.

Simple one-off queries stay inline in the route that uses them - it is easier
to read the SQL next to the code that needs it. Only the joins that are shared
(or long enough to be worth naming) live here.
"""

import db

# The rating of a provider is always derived from the reviews table rather than
# stored on the provider row, so it can never drift out of date.
PROVIDER_COLUMNS = """
    p.id, p.user_id, p.service_id, p.business_name, p.bio,
    p.hourly_rate, p.experience_years, p.address,
    p.latitude, p.longitude, p.is_available, p.is_approved,
    u.name AS provider_name, u.phone AS provider_phone, u.email AS provider_email,
    u.is_active AS account_active,
    s.name AS service_name, s.icon AS service_icon,
    COALESCE(r.avg_rating, 0) AS avg_rating,
    COALESCE(r.review_count, 0) AS review_count
"""

PROVIDER_JOINS = """
    FROM providers p
    JOIN users u    ON u.id = p.user_id
    JOIN services s ON s.id = p.service_id
    LEFT JOIN (
        SELECT provider_id,
               AVG(rating) AS avg_rating,
               COUNT(*)    AS review_count
        FROM reviews
        GROUP BY provider_id
    ) r ON r.provider_id = p.id
"""


def active_services():
    return db.fetch_all(
        "SELECT id, name, icon, description FROM services "
        "WHERE is_active = 1 ORDER BY name"
    )


def search_providers(service_id):
    """Providers a customer is allowed to see for one service.

    Approved by the admin, marked available by the provider, and belonging to
    an account that is still active.
    """
    return db.fetch_all(
        f"SELECT {PROVIDER_COLUMNS} {PROVIDER_JOINS} "
        "WHERE p.service_id = %s AND p.is_approved = 1 "
        "AND p.is_available = 1 AND u.is_active = 1",
        (service_id,),
    )


def get_provider(provider_id):
    return db.fetch_one(
        f"SELECT {PROVIDER_COLUMNS} {PROVIDER_JOINS} WHERE p.id = %s",
        (provider_id,),
    )


def get_provider_by_user(user_id):
    return db.fetch_one(
        f"SELECT {PROVIDER_COLUMNS} {PROVIDER_JOINS} WHERE p.user_id = %s",
        (user_id,),
    )


BOOKING_COLUMNS = """
    b.id, b.user_id, b.provider_id, b.service_id,
    b.scheduled_date, b.scheduled_time, b.address, b.latitude, b.longitude,
    b.note, b.estimated_hours, b.distance_km, b.status, b.created_at,
    s.name AS service_name, s.icon AS service_icon,
    p.business_name, p.hourly_rate, p.address AS provider_address,
    p.latitude AS provider_lat, p.longitude AS provider_lng,
    pu.name AS provider_name, pu.phone AS provider_phone,
    cu.name AS customer_name, cu.phone AS customer_phone,
    rv.id AS review_id, rv.rating AS review_rating, rv.comment AS review_comment,
    pay.id AS payment_id, pay.amount AS payment_amount,
    pay.status AS payment_status, pay.payment_method,
    pay.transaction_id AS payment_transaction_id,
    pay.paid_at, pay.refunded_at
"""

BOOKING_JOINS = """
    FROM bookings b
    JOIN services s   ON s.id = b.service_id
    JOIN providers p  ON p.id = b.provider_id
    JOIN users pu     ON pu.id = p.user_id
    JOIN users cu     ON cu.id = b.user_id
    LEFT JOIN reviews rv  ON rv.booking_id = b.id
    LEFT JOIN payments pay ON pay.booking_id = b.id
"""


# How the customer may order their bookings. The key comes from the URL, so
# only these are accepted - the value never reaches the SQL itself.
BOOKING_SORTS = {
    "newest":    ("Newest booking first",       "b.created_at DESC"),
    "oldest":    ("Oldest booking first",       "b.created_at ASC"),
    "soonest":   ("Service date: soonest first", "b.scheduled_date ASC, b.scheduled_time ASC"),
    "latest":    ("Service date: latest first",  "b.scheduled_date DESC, b.scheduled_time DESC"),
    "provider":  ("Provider name: A-Z",          "pu.name ASC"),
    "provider_z":("Provider name: Z-A",          "pu.name DESC"),
    "shop":      ("Shop name: A-Z",              "p.business_name ASC"),
    "status":    ("Status",                      "b.status ASC, b.created_at DESC"),
}
DEFAULT_BOOKING_SORT = "newest"


def resolve_booking_sort(value):
    return value if value in BOOKING_SORTS else DEFAULT_BOOKING_SORT


def services_with_provider_counts():
    """Active services for the public catalogue, with what a customer can book.

    LEFT JOIN so a service with no providers yet still appears with a count of
    zero. Only providers a customer could find in search are counted - approved,
    available, on an active account - and only their rates
    make up the "from Rs" price, so the figure is one a customer could get.
    """
    return db.fetch_all(
        "SELECT s.id, s.name, s.icon, s.description, "
        "COUNT(p.id) AS provider_count, "
        "MIN(p.hourly_rate) AS min_rate, MAX(p.hourly_rate) AS max_rate "
        "FROM services s "
        "LEFT JOIN providers p ON p.service_id = s.id "
        "     AND p.is_approved = 1 AND p.is_available = 1 "
        "     AND p.user_id IN (SELECT id FROM users WHERE is_active = 1) "
        "WHERE s.is_active = 1 "
        "GROUP BY s.id, s.name, s.icon, s.description ORDER BY s.name"
    )


def service_overview(service_id):
    """One active service with the figures its category page shows, or None.

    Rating is the mean of every review for the providers listed on the page -
    the same approved, available, active ones that search shows - and
    jobs are completed bookings scheduled in the current calendar year.
    """
    service = db.fetch_one(
        "SELECT s.id, s.name, s.icon, s.description, "
        "COUNT(p.id) AS provider_count, "
        "MIN(p.hourly_rate) AS min_rate, MAX(p.hourly_rate) AS max_rate "
        "FROM services s "
        "LEFT JOIN providers p ON p.service_id = s.id "
        "     AND p.is_approved = 1 AND p.is_available = 1 "
        "     AND p.user_id IN (SELECT id FROM users WHERE is_active = 1) "
        "WHERE s.id = %s AND s.is_active = 1 "
        "GROUP BY s.id, s.name, s.icon, s.description",
        (service_id,),
    )
    if service is None:
        return None
    rating = db.fetch_one(
        "SELECT AVG(r.rating) AS avg_rating, COUNT(r.id) AS review_count "
        "FROM reviews r "
        "JOIN providers p ON p.id = r.provider_id "
        "JOIN users u ON u.id = p.user_id "
        "WHERE p.service_id = %s AND p.is_approved = 1 "
        "AND p.is_available = 1 AND u.is_active = 1",
        (service_id,),
    )
    jobs = db.fetch_one(
        "SELECT COUNT(*) AS total FROM bookings "
        "WHERE service_id = %s AND status = 'completed' "
        "AND YEAR(scheduled_date) = YEAR(CURDATE())",
        (service_id,),
    )
    service["avg_rating"] = rating["avg_rating"] if rating else None
    service["review_count"] = rating["review_count"] if rating else 0
    service["jobs_this_year"] = jobs["total"] if jobs else 0
    return service


def top_rated_providers(service_id=None, limit=4):
    """Approved, available providers, best rated first.

    Reviewed providers come before unreviewed ones, then more reviews, then
    more experience, so a single five-star review does not outrank a long
    record. Used by the category page and the homepage preview; it is a
    ranking by reputation only, because distance needs the customer's location.
    """
    sql = ("SELECT " + PROVIDER_COLUMNS + PROVIDER_JOINS +
           "WHERE p.is_approved = 1 AND p.is_available = 1 AND u.is_active = 1 "
           "AND s.is_active = 1 ")
    params = []
    if service_id is not None:
        sql += "AND p.service_id = %s "
        params.append(service_id)
    sql += ("ORDER BY (r.review_count IS NULL), avg_rating DESC, "
            "review_count DESC, p.experience_years DESC, p.id "
            "LIMIT %s")
    params.append(int(limit))
    return db.fetch_all(sql, tuple(params))


def bookings_for_user(user_id, search="", sort=DEFAULT_BOOKING_SORT, status=""):
    """This customer's bookings, optionally filtered and ordered.

    `search` matches the provider's own name or their business name, so
    "Ramesh" and "Shrestha Electric" both find the same booking.
    """
    sql = f"SELECT {BOOKING_COLUMNS} {BOOKING_JOINS} WHERE b.user_id = %s "
    params = [user_id]

    if search:
        # LIKE with a bound parameter - the text never becomes part of the SQL.
        sql += "AND (pu.name LIKE %s OR p.business_name LIKE %s) "
        params += [f"%{search}%", f"%{search}%"]

    if status in {"pending", "accepted", "rejected", "completed", "cancelled"}:
        sql += "AND b.status = %s "
        params.append(status)

    sql += "ORDER BY " + BOOKING_SORTS[resolve_booking_sort(sort)][1]
    return db.fetch_all(sql, tuple(params))


def bookings_for_provider(provider_id, search=""):
    """This provider's own bookings, optionally filtered by customer name."""
    sql = f"SELECT {BOOKING_COLUMNS} {BOOKING_JOINS} WHERE b.provider_id = %s "
    params = [provider_id]

    if search:
        sql += "AND cu.name LIKE %s "
        params.append(f"%{search}%")

    sql += "ORDER BY b.scheduled_date DESC, b.scheduled_time DESC"
    return db.fetch_all(sql, tuple(params))


def get_booking(booking_id):
    """One booking with its provider, customer, service, review and payment."""
    return db.fetch_one(
        f"SELECT {BOOKING_COLUMNS} {BOOKING_JOINS} WHERE b.id = %s",
        (booking_id,),
    )


def reviews_for_provider(provider_id, limit=20, rating=None, sort=None):
    """This provider's reviews, optionally only one star value.

    provider_id always comes from the signed-in account, and it is the first
    thing in the WHERE clause, so no combination of rating or sort can reach
    another provider's reviews.
    """
    sql = (
        "SELECT rv.id, rv.rating, rv.comment, rv.created_at, rv.booking_id, "
        "u.name AS customer_name, s.name AS service_name "
        "FROM reviews rv "
        "JOIN users u    ON u.id = rv.user_id "
        "JOIN bookings b ON b.id = rv.booking_id "
        "JOIN services s ON s.id = b.service_id "
        "WHERE rv.provider_id = %s "
    )
    params = [provider_id]
    if rating in (1, 2, 3, 4, 5):
        sql += "AND rv.rating = %s "
        params.append(rating)

    order = REVIEW_SORTS.get(sort or DEFAULT_REVIEW_SORT,
                             REVIEW_SORTS[DEFAULT_REVIEW_SORT])[1]
    sql += f"ORDER BY {order} LIMIT %s"
    params.append(limit)

    return db.fetch_all(sql, tuple(params))


# ---------------------------------------------------------------------------
# Provider availability
#
# A provider states the days and hours they work. A provider who has stated
# nothing at all is treated as working every day from 06:00 to 20:00, so every
# provider who signed up before this feature existed keeps working exactly as
# before instead of vanishing from search.
# ---------------------------------------------------------------------------
WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday",
            "Friday", "Saturday", "Sunday")

DEFAULT_START = "06:00"
DEFAULT_END = "20:00"


def availability_for(provider_id):
    """The provider's working days, earliest weekday first."""
    return db.fetch_all(
        "SELECT weekday, start_time, end_time FROM provider_availability "
        "WHERE provider_id = %s ORDER BY weekday",
        (provider_id,),
    )


def availability_map(provider_ids):
    """Working hours for several providers at once, to avoid a query per row.

    Returns {provider_id: {weekday: (start, end)}}. A provider missing from the
    result has stated nothing and is therefore always available.
    """
    if not provider_ids:
        return {}
    placeholders = ", ".join(["%s"] * len(provider_ids))
    rows = db.fetch_all(
        "SELECT provider_id, weekday, start_time, end_time "
        f"FROM provider_availability WHERE provider_id IN ({placeholders})",
        tuple(provider_ids),
    )
    result = {}
    for row in rows:
        result.setdefault(row["provider_id"], {})[row["weekday"]] = (
            row["start_time"], row["end_time"]
        )
    return result


def _as_minutes(value):
    """MySQL hands back TIME as a timedelta; turn it into minutes past midnight."""
    if hasattr(value, "total_seconds"):
        return int(value.total_seconds()) // 60
    return value.hour * 60 + value.minute


def _clock(minutes):
    """Minutes past midnight as a friendly 12-hour time, e.g. "08:00 AM"."""
    hour, minute = divmod(int(minutes), 60)
    suffix = "AM" if hour < 12 else "PM"
    shown = hour % 12 or 12
    return f"{shown:02d}:{minute:02d} {suffix}"


def _default_window():
    """The legacy rule: a provider who has stated nothing works 06:00 - 20:00."""
    return 6 * 60, 20 * 60


def availability_windows(days):
    """Every working day as {weekday, name, start, end, label}, in week order.

    A provider who has stated nothing gets all seven days at the default hours,
    which is the behaviour the rest of the application has always had.
    """
    windows = []
    if not days:
        start, end = _default_window()
        for weekday in range(7):
            windows.append({
                "weekday": weekday, "name": WEEKDAYS[weekday],
                "start": start, "end": end,
                "label": f"{_clock(start)} - {_clock(end)}",
            })
        return windows

    for weekday in sorted(days):
        start = _as_minutes(days[weekday][0])
        end = _as_minutes(days[weekday][1])
        windows.append({
            "weekday": weekday, "name": WEEKDAYS[weekday],
            "start": start, "end": end,
            "label": f"{_clock(start)} - {_clock(end)}",
        })
    return windows


def window_for(days, booking_date):
    """The working window covering that date, or None if it is a day off."""
    if not days:
        return _default_window()
    entry = days.get(booking_date.weekday())
    if entry is None:
        return None
    return _as_minutes(entry[0]), _as_minutes(entry[1])


def works_at(days, booking_date, booking_time):
    """Is the provider working at that moment? (start of the job only)"""
    window = window_for(days, booking_date)
    if window is None:
        return False
    start, end = window
    minutes = booking_time.hour * 60 + booking_time.minute
    return start <= minutes <= end


def check_booking_window(days, booking_date, booking_time, hours=0):
    """Why this slot cannot be booked, or None when it is fine.

    Checks three things in turn: the provider works that weekday, the job
    starts inside their hours, and the whole job finishes inside them too - a
    two hour job starting an hour before closing does not fit.

    Returns {"reason": str, "windows": [...]} so the page can show the exact
    days and times instead of a vague refusal.
    """
    windows = availability_windows(days)
    window = window_for(days, booking_date)
    day_name = WEEKDAYS[booking_date.weekday()]

    if window is None:
        return {
            "reason": f"This service provider is not available on {day_name}.",
            "windows": windows,
        }

    start, end = window
    begins = booking_time.hour * 60 + booking_time.minute
    finishes = begins + int(hours or 0) * 60

    if begins < start or begins > end:
        return {
            "reason": (
                f"This service provider works on {day_name} from "
                f"{_clock(start)} to {_clock(end)}. Please choose a time "
                "within their working hours."
            ),
            "windows": windows,
        }

    if hours and finishes > end:
        return {
            "reason": (
                f"A {int(hours)} hour job starting at {_clock(begins)} would "
                f"finish at {_clock(finishes)}, but this provider stops at "
                f"{_clock(end)} on {day_name}. Choose an earlier time or a "
                "shorter job."
            ),
            "windows": windows,
        }

    return None


def availability_summary(days):
    """A short line for a provider card, e.g. "Mon, Wed, Fri"."""
    if not days:
        return "Every day, 06:00 AM - 08:00 PM"
    return ", ".join(WEEKDAYS[d][:3] for d in sorted(days))


# ---------------------------------------------------------------------------
# Notifications
# ---------------------------------------------------------------------------
def add_notification(user_id, message, booking_id=None, title=""):
    """Tell one person that something happened."""
    return db.execute(
        "INSERT INTO notifications (user_id, booking_id, title, message) "
        "VALUES (%s, %s, %s, %s)",
        (user_id, booking_id, title[:120], message[:255]),
    )


def notify_admins(title, message, booking_id=None):
    """Tell every administrator that something worth knowing happened.

    Only called for the handful of events an administrator actually has to act
    on or account for - a provider moving shop, a provider changing the hours
    they work, a cancellation, a refund, and a new provider waiting for
    approval. Ordinary edits (a new bio, a price change, a booking being
    accepted) deliberately do NOT come through here, otherwise the bell would
    fill up with noise and the important ones would be missed.

    One row per administrator, so each of them can read and clear their own.
    """
    admins = db.fetch_all(
        "SELECT id FROM users WHERE role = 'admin' AND is_active = 1"
    )
    for admin in admins:
        add_notification(admin["id"], message, booking_id, title)
    return len(admins)


# ---------------------------------------------------------------------------
# Searching
# ---------------------------------------------------------------------------
def like_term(text):
    """Turn what someone typed into a safe LIKE pattern.

    The value is still passed as a query parameter - this only escapes the two
    characters that mean something to LIKE, so searching for "50%" looks for a
    literal percent sign instead of matching everything.
    """
    cleaned = (text or "").strip()
    cleaned = cleaned.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{cleaned}%"


def booking_id_in(text):
    """The booking number inside a search term, or None.

    Accepts "1024", "#1024" and "BK1024", so an administrator can paste a
    booking reference in whichever form they are looking at.
    """
    cleaned = (text or "").strip().lstrip("#").strip()
    if cleaned[:2].upper() == "BK":
        cleaned = cleaned[2:]
    return int(cleaned) if cleaned.isdigit() else None


# ---------------------------------------------------------------------------
# Review filtering and sorting
# ---------------------------------------------------------------------------
# Whitelist: the value from the URL is only ever used to look up one of these
# fixed fragments, so it can never reach the query itself.
REVIEW_SORTS = {
    "newest":  ("Newest first",    "rv.created_at DESC"),
    "oldest":  ("Oldest first",    "rv.created_at ASC"),
    "highest": ("Highest rating",  "rv.rating DESC, rv.created_at DESC"),
    "lowest":  ("Lowest rating",   "rv.rating ASC, rv.created_at DESC"),
}
DEFAULT_REVIEW_SORT = "newest"


def read_review_filters(args):
    """Read ?rating= and ?sort= from a request, refusing anything unexpected."""
    try:
        rating = int(args.get("rating", ""))
    except (TypeError, ValueError):
        rating = None
    if rating not in (1, 2, 3, 4, 5):
        rating = None

    sort = args.get("sort", DEFAULT_REVIEW_SORT)
    if sort not in REVIEW_SORTS:
        sort = DEFAULT_REVIEW_SORT
    return rating, sort


def rating_breakdown(provider_id=None):
    """How many reviews there are at each star, plus the average.

    Counted from the reviews table every time rather than being stored, so it
    can never disagree with the reviews themselves.
    """
    where, params = "", ()
    if provider_id is not None:
        where = "WHERE provider_id = %s "
        params = (provider_id,)

    rows = db.fetch_all(
        "SELECT rating, COUNT(*) AS total FROM reviews " + where +
        "GROUP BY rating", params
    )
    counts = {star: 0 for star in range(1, 6)}
    for row in rows:
        counts[row["rating"]] = row["total"]

    total = sum(counts.values())
    average = (sum(star * n for star, n in counts.items()) / total) if total else 0
    return {"counts": counts, "total": total, "average": average}


def unread_notification_count(user_id):
    row = db.fetch_one(
        "SELECT COUNT(*) AS total FROM notifications "
        "WHERE user_id = %s AND is_read = 0",
        (user_id,),
    )
    return row["total"] if row else 0


def notifications_for(user_id, limit=50):
    return db.fetch_all(
        "SELECT id, booking_id, title, message, is_read, created_at FROM notifications "
        "WHERE user_id = %s ORDER BY created_at DESC LIMIT %s",
        (user_id, limit),
    )


def provider_owner_id(provider_id):
    """The users.id behind a provider, so the provider can be notified."""
    row = db.fetch_one("SELECT user_id FROM providers WHERE id = %s", (provider_id,))
    return row["user_id"] if row else None


# ---------------------------------------------------------------------------
# Favourite providers
#
# A customer may only favourite a provider they have actually used, which means
# at least one completed booking between the two of them.
# ---------------------------------------------------------------------------
def has_completed_booking(user_id, provider_id):
    return db.fetch_one(
        "SELECT id FROM bookings WHERE user_id = %s AND provider_id = %s "
        "AND status = 'completed' LIMIT 1",
        (user_id, provider_id),
    ) is not None


def is_favourite(user_id, provider_id):
    return db.fetch_one(
        "SELECT id FROM favourite_providers WHERE user_id = %s AND provider_id = %s",
        (user_id, provider_id),
    ) is not None


def favourite_ids(user_id):
    """The set of provider ids this customer has favourited, for the templates."""
    rows = db.fetch_all(
        "SELECT provider_id FROM favourite_providers WHERE user_id = %s", (user_id,)
    )
    return {row["provider_id"] for row in rows}


def favourites_for(user_id):
    """Full provider cards for the favourites page, newest saved first."""
    return db.fetch_all(
        f"SELECT {PROVIDER_COLUMNS}, f.created_at AS favourited_at {PROVIDER_JOINS} "
        "JOIN favourite_providers f ON f.provider_id = p.id "
        "WHERE f.user_id = %s ORDER BY f.created_at DESC",
        (user_id,),
    )


def providers_used_by(user_id):
    """Providers this customer has completed a job with - the ones they may
    favourite. Used to decide where a heart button is shown."""
    rows = db.fetch_all(
        "SELECT DISTINCT provider_id FROM bookings "
        "WHERE user_id = %s AND status = 'completed'",
        (user_id,),
    )
    return {row["provider_id"] for row in rows}
