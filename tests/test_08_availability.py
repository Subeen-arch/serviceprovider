"""Availability schedule, database-level slot lock, reschedule, notifications, receipt."""
import os, sys
from datetime import date, timedelta
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tests import support
support.use_test_database()   # must happen before app is imported

import mysql.connector
from app import app

BASE = support.BASE
PASS, FAIL = [], []
def check(n, c, d=""):
    (PASS if c else FAIL).append(n)
    print(("  PASS  " if c else "  FAIL  ") + n + (f"   [{d}]" if d and not c else ""))
def conn():
    return support.connect()
def q(sql, p=()):
    c = conn(); cur = c.cursor(dictionary=True); cur.execute(sql, p)
    r = cur.fetchall(); cur.close(); c.close(); return r
def ex(sql, p=()):
    c = conn(); cur = c.cursor(); cur.execute(sql, p); c.commit(); cur.close(); c.close()
def login(c, e, pw=support.SEED_PASSWORD): return c.post("/login", data={"email": e, "password": pw}, base_url=BASE)
def body(r): return " ".join(r.get_data(as_text=True).split())

ex("DELETE FROM bookings WHERE note LIKE 'AV%'")
ex("DELETE FROM provider_availability")
ex("DELETE FROM notifications")

prov = q("SELECT p.id, p.hourly_rate, p.business_name, u.email, u.id AS owner "
         "FROM providers p JOIN users u ON u.id=p.user_id JOIN services s ON s.id=p.service_id "
         "WHERE s.name='Electrician' AND p.is_approved=1 AND p.address LIKE 'Thamel%' LIMIT 1")[0]
PID = prov["id"]
cust = app.test_client(); login(cust, "aarati@example.com")
pv   = app.test_client(); login(pv, prov["email"])
cust2 = app.test_client(); login(cust2, "nirajan@example.com")

# a Monday well in the future
d = date.today() + timedelta(days=7)
while d.weekday() != 0:
    d += timedelta(days=1)
MON, TUE = d, d + timedelta(days=1)
form = lambda **kw: {"latitude": "27.7154", "longitude": "85.3123",
                     "address": "Thamel, Kathmandu", "estimated_hours": "2", **kw}

print("\n########## 61. SCHEMA ##########")
DB = os.environ["DB_NAME"]
tables = {list(r.values())[0] for r in q("SHOW TABLES")}
check("provider_availability table exists", "provider_availability" in tables)
check("notifications table exists", "notifications" in tables)
col = q("SELECT EXTRA FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=%s "
        "AND TABLE_NAME='bookings' AND COLUMN_NAME='active_slot'", (DB,))
check("bookings.active_slot is a generated column", col and "GENERATED" in col[0]["EXTRA"], str(col))
idx = q("SELECT NON_UNIQUE FROM information_schema.STATISTICS WHERE TABLE_SCHEMA=%s "
        "AND INDEX_NAME='uq_bookings_active_slot' LIMIT 1", (DB,))
check("unique index on active_slot exists", idx and idx[0]["NON_UNIQUE"] == 0, str(idx))

print("\n########## 62. NO SCHEDULE = AVAILABLE AS BEFORE ##########")
r = cust.post(f"/book/{PID}/request", data=form(scheduled_date=MON.isoformat(),
              scheduled_time="10:00", note="AV default"), base_url=BASE)
bk = q("SELECT * FROM bookings WHERE note='AV default' ORDER BY id DESC LIMIT 1")
check("provider with no stated hours still accepts bookings", len(bk) == 1, str(r.status_code))
BK1 = bk[0]["id"] if bk else None
check("provider notified of the new request",
      any("New request" in n["message"] for n in q("SELECT message FROM notifications WHERE user_id=%s", (prov["owner"],))))

print("\n########## 63. DATABASE-LEVEL DOUBLE-BOOKING LOCK ##########")
# Bypass the application check entirely and go straight at the database.
raised = ""
try:
    ex("INSERT INTO bookings (user_id, provider_id, service_id, scheduled_date, scheduled_time, "
       "address, latitude, longitude, note, estimated_hours, status) "
       "SELECT user_id, provider_id, service_id, scheduled_date, scheduled_time, address, "
       "latitude, longitude, 'AV raw clash', estimated_hours, 'pending' FROM bookings WHERE id=%s", (BK1,))
except Exception as exc:
    raised = str(exc)
check("database itself refuses a second live booking in the same slot",
      "uq_bookings_active_slot" in raised or "Duplicate" in raised, raised[:90] or "no error raised")
check("the clashing row was not written",
      q("SELECT COUNT(*) n FROM bookings WHERE note='AV raw clash'")[0]["n"] == 0)

# once freed, the slot works again
ex("UPDATE bookings SET status='cancelled' WHERE id=%s", (BK1,))
freed = ""
try:
    ex("INSERT INTO bookings (user_id, provider_id, service_id, scheduled_date, scheduled_time, "
       "address, latitude, longitude, note, estimated_hours, status) "
       "SELECT user_id, provider_id, service_id, scheduled_date, scheduled_time, address, "
       "latitude, longitude, 'AV reuse', estimated_hours, 'pending' FROM bookings WHERE id=%s", (BK1,))
except Exception as exc:
    freed = str(exc)
check("a cancelled slot becomes bookable again", freed == "", freed[:90])
ex("DELETE FROM bookings WHERE note IN ('AV reuse','AV default')")

print("\n########## 64. WORKING HOURS ARE ENFORCED ##########")
r = pv.post("/provider/availability", data={
    "work_0": "1", "start_0": "09:00", "end_0": "17:00",   # Monday only
}, base_url=BASE, follow_redirects=True)
rows = q("SELECT weekday FROM provider_availability WHERE provider_id=%s", (PID,))
check("working hours saved", [x["weekday"] for x in rows] == [0], str(rows))
check("provider told it saved", "Working hours saved" in body(r))

r = cust.post(f"/book/{PID}/request", data=form(scheduled_date=TUE.isoformat(),
              scheduled_time="10:00", note="AV offday"), base_url=BASE, follow_redirects=True)
check("booking on a non-working day is refused", "is not available on" in body(r))
check("nothing written for the off day",
      q("SELECT COUNT(*) n FROM bookings WHERE note='AV offday'")[0]["n"] == 0)

r = cust.post(f"/book/{PID}/request", data=form(scheduled_date=MON.isoformat(),
              scheduled_time="07:00", note="AV early"), base_url=BASE, follow_redirects=True)
check("booking before opening time is refused",
      "within their working hours" in body(r) or "is not available on" in body(r))

r = cust.post(f"/book/{PID}/request", data=form(scheduled_date=MON.isoformat(),
              scheduled_time="10:00", note="AV inhours"), base_url=BASE, follow_redirects=True)
bk = q("SELECT * FROM bookings WHERE note='AV inhours' ORDER BY id DESC LIMIT 1")
check("booking inside working hours succeeds", len(bk) == 1)
BK2 = bk[0]["id"] if bk else None

print("\n########## 65. RESCHEDULE ##########")
r = cust.post(f"/bookings/{BK2}/reschedule",
              data={"scheduled_date": MON.isoformat(), "scheduled_time": "14:00"},
              base_url=BASE, follow_redirects=True)
row = q("SELECT scheduled_time, status FROM bookings WHERE id=%s", (BK2,))[0]
check("customer can move a pending request",
      int(row["scheduled_time"].total_seconds()) // 3600 == 14, str(row["scheduled_time"]))
check("still pending after the move", row["status"] == "pending")
check("provider notified of the move",
      any("moved request" in n["message"] for n in q("SELECT message FROM notifications WHERE user_id=%s", (prov["owner"],))))

r = cust.post(f"/bookings/{BK2}/reschedule",
              data={"scheduled_date": TUE.isoformat(), "scheduled_time": "10:00"},
              base_url=BASE, follow_redirects=True)
check("cannot move onto a non-working day", "is not available on" in body(r))

r = cust2.post(f"/bookings/{BK2}/reschedule",
               data={"scheduled_date": MON.isoformat(), "scheduled_time": "15:00"},
               base_url=BASE, follow_redirects=True)
check("another customer cannot move it", "Booking not found" in body(r))

pv.post(f"/provider/bookings/{BK2}/accept", base_url=BASE, follow_redirects=True)
r = cust.post(f"/bookings/{BK2}/reschedule",
              data={"scheduled_date": MON.isoformat(), "scheduled_time": "16:00"},
              base_url=BASE, follow_redirects=True)
check("cannot reschedule once accepted", "cannot be rescheduled" in body(r))

print("\n########## 66. NOTIFICATIONS ##########")
notes = q("SELECT message FROM notifications WHERE user_id=%s ORDER BY id", (q(
    "SELECT id FROM users WHERE email='aarati@example.com'")[0]["id"],))
check("customer told the request was accepted",
      any("accepted booking" in n["message"] for n in notes), str([n["message"][:40] for n in notes]))
t = body(cust.get("/bookings", base_url=BASE))
check("nav shows an unread badge", "Alerts" in t)
r = cust.get("/notifications", base_url=BASE)
check("notifications page loads", r.status_code == 200 and "accepted booking" in body(r))
check("opening the page marks them read",
      q("SELECT COUNT(*) n FROM notifications WHERE user_id=%s AND is_read=0",
        (q("SELECT id FROM users WHERE email='aarati@example.com'")[0]["id"],))[0]["n"] == 0)
r = app.test_client().get("/notifications", base_url=BASE)
check("anonymous blocked from notifications",
      r.status_code == 302 and "/login" in r.headers.get("Location", ""))

print("\n########## 67. RECEIPT ##########")
r = cust.get(f"/bookings/{BK2}/receipt", base_url=BASE, follow_redirects=True)
check("no receipt before payment", "only available once the payment" in body(r))
ex("INSERT INTO payments (booking_id, user_id, amount, payment_method, status, paid_at, transaction_id) "
   "VALUES (%s, %s, %s, 'khalti', 'paid', NOW(), 'TESTTXN99')",
   (BK2, q("SELECT user_id FROM bookings WHERE id=%s", (BK2,))[0]["user_id"], float(prov["hourly_rate"]) * 2))
r = cust.get(f"/bookings/{BK2}/receipt", base_url=BASE)
t = body(r)
check("receipt renders once paid", r.status_code == 200 and "Payment receipt" in t)
# Read the name from the database: an earlier suite edits it via the
# profile form, so hard-coding it here would be testing stale data.
customer_name = q("SELECT name FROM users WHERE email='aarati@example.com'")[0]["name"]
for label in [prov["business_name"], customer_name, "TESTTXN99", "Total paid"]:
    check(f"receipt shows '{label[:28]}'", label in t)
check("receipt amount matches the payment",
      f"Rs {float(prov['hourly_rate']) * 2:.2f}" in t, f"Rs {float(prov['hourly_rate'])*2:.2f}")
r = cust2.get(f"/bookings/{BK2}/receipt", base_url=BASE, follow_redirects=True)
check("another customer cannot see the receipt", "Booking not found" in body(r))

print("\n########## 68. AVAILABILITY PAGE ACCESS ##########")
r = cust.get("/provider/availability", base_url=BASE)
check("customer blocked from the hours page", r.status_code == 302)
r = app.test_client().get("/provider/availability", base_url=BASE)
check("anonymous blocked from the hours page",
      r.status_code == 302 and "/login" in r.headers.get("Location", ""))
r = pv.post("/provider/availability", data={"work_0": "1", "start_0": "17:00", "end_0": "09:00"},
            base_url=BASE, follow_redirects=True)
check("end before start is refused", "end time must be after the start" in body(r))
r = pv.post("/provider/availability", data={"work_0": "1", "start_0": "nope", "end_0": "17:00"},
            base_url=BASE, follow_redirects=True)
check("nonsense time is refused", "must be a time like" in body(r))
r = pv.post("/provider/availability", data={}, base_url=BASE, follow_redirects=True)
check("clearing every day returns to the default",
      "available every day" in body(r) and
      q("SELECT COUNT(*) n FROM provider_availability WHERE provider_id=%s", (PID,))[0]["n"] == 0)

print(f"\n===== availability + notifications: {len(PASS)} passed, {len(FAIL)} failed =====")
if FAIL:
    print("FAILURES:"); [print("   -", f) for f in FAIL]

# Clean up so the next suite starts from the seeded state.
ex("DELETE FROM provider_availability")
ex("DELETE FROM bookings WHERE note LIKE 'AV%'")
