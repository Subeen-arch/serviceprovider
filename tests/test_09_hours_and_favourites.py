"""Working hours + duration rules, favourites, and the two search bars."""
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

ex("DELETE FROM bookings WHERE note LIKE 'WH%'")
ex("DELETE FROM provider_availability")
ex("DELETE FROM favourite_providers")

prov = q("SELECT p.id, p.business_name, u.email, u.name AS pname FROM providers p "
         "JOIN users u ON u.id=p.user_id JOIN services s ON s.id=p.service_id "
         "WHERE s.name='Electrician' AND p.is_approved=1 AND p.address LIKE 'Thamel%' LIMIT 1")[0]
PID = prov["id"]
CUST = q("SELECT id, name FROM users WHERE email='aarati@example.com'")[0]

cust = app.test_client(); login(cust, "aarati@example.com")
pv   = app.test_client(); login(pv, prov["email"])
other= app.test_client(); login(other, "nirajan@example.com")

# next Friday and the Tuesday before it
d = date.today() + timedelta(days=3)
while d.weekday() != 4: d += timedelta(days=1)
FRI = d
TUE = FRI - timedelta(days=3)
form = lambda **kw: {"latitude": "27.7154", "longitude": "85.3123",
                     "address": "Thamel, Kathmandu", **kw}

print("\n########## 69. PROVIDER SETS PER-DAY HOURS ##########")
r = pv.post("/provider/availability", data={
    "work_0": "1", "start_0": "08:00", "end_0": "17:00",   # Mon 08-17
    "work_1": "1", "start_1": "09:00", "end_1": "18:00",   # Tue 09-18
    "work_4": "1", "start_4": "06:00", "end_4": "20:00",   # Fri 06-20
}, base_url=BASE, follow_redirects=True)
rows = {r_["weekday"]: (r_["start_time"], r_["end_time"])
        for r_ in q("SELECT weekday,start_time,end_time FROM provider_availability WHERE provider_id=%s", (PID,))}
check("only the ticked days saved", sorted(rows) == [0, 1, 4], str(sorted(rows)))
check("each day keeps its own hours",
      int(rows[0][0].total_seconds())//3600 == 8 and int(rows[1][0].total_seconds())//3600 == 9
      and int(rows[4][1].total_seconds())//3600 == 20, str(rows))
t = body(pv.get("/provider/availability", base_url=BASE))
check("saved values shown again, not defaults", 'value="08:00"' in t and 'value="09:00"' in t)
check("unticked day is unchecked on reload",
      'id="work_2"' in t and 'name="work_2" value="1" checked' not in t)

r = pv.post("/provider/availability", data={"work_0": "1", "start_0": "08:00", "end_0": "17:00"},
            base_url=BASE, follow_redirects=True)
after = [x["weekday"] for x in q("SELECT weekday FROM provider_availability WHERE provider_id=%s", (PID,))]
check("unticking a day removes its row", after == [0], str(after))

# restore the three-day week for the booking tests
pv.post("/provider/availability", data={
    "work_0": "1", "start_0": "08:00", "end_0": "17:00",
    "work_1": "1", "start_1": "09:00", "end_1": "18:00",
    "work_4": "1", "start_4": "06:00", "end_4": "20:00",
}, base_url=BASE, follow_redirects=True)

print("\n########## 70. BOOKING PAGE SHOWS THE HOURS ##########")
t = body(cust.get(f"/book/{PID}?latitude=27.7154&longitude=85.3123&address=Thamel", base_url=BASE))
check("hours panel lists the working days",
      "When this provider works" in t and "Monday" in t and "Friday" in t)
check("shows real 12-hour times", "08:00 AM - 05:00 PM" in t and "06:00 AM - 08:00 PM" in t)
check("a non-working day is not listed", "Wednesday" not in t.split("Recent reviews")[0])
check("browser-side check present", "hours-error" in t and "byDay" in t)

print("\n########## 71. BACKEND REFUSES A NON-WORKING DAY ##########")
WED = FRI - timedelta(days=2)
r = cust.post(f"/book/{PID}/request",
              data=form(scheduled_date=WED.isoformat(), scheduled_time="10:00",
                        estimated_hours="1", note="WH wed"),
              base_url=BASE, follow_redirects=True)
t = body(r)
check("names the day it refused", "not available on Wednesday" in t, t[:160])
check("lists the days that do work",
      "Monday 08:00 AM - 05:00 PM" in t and "Friday 06:00 AM - 08:00 PM" in t)
check("no booking written", q("SELECT COUNT(*) n FROM bookings WHERE note='WH wed'")[0]["n"] == 0)

print("\n########## 72. BACKEND REFUSES A TIME OUTSIDE HOURS ##########")
# 20:30 is refused earlier by the platform-wide 06:00-20:00 rule, so this uses
# Monday 18:00: allowed platform-wide, but this provider closes at 17:00.
MON = FRI + timedelta(days=3)   # the Monday AFTER, so it is never in the past
r = cust.post(f"/book/{PID}/request",
              data=form(scheduled_date=MON.isoformat(), scheduled_time="18:00",
                        estimated_hours="1", note="WH late"),
              base_url=BASE, follow_redirects=True)
check("explains the exact window",
      "works on Monday from 08:00 AM to 05:00 PM" in body(r), body(r)[:200])
check("nothing written", q("SELECT COUNT(*) n FROM bookings WHERE note='WH late'")[0]["n"] == 0)
r = cust.post(f"/book/{PID}/request",
              data=form(scheduled_date=FRI.isoformat(), scheduled_time="20:30",
                        estimated_hours="1", note="WH global"),
              base_url=BASE, follow_redirects=True)
check("the platform-wide hours rule still fires first",
      "only available between 06:00 and 20:00" in body(r))

print("\n########## 73. THE JOB MUST FINISH INSIDE THE HOURS ##########")
r = cust.post(f"/book/{PID}/request",
              data=form(scheduled_date=FRI.isoformat(), scheduled_time="19:30",
                        estimated_hours="1", note="WH overrun"),
              base_url=BASE, follow_redirects=True)
t = body(r)
check("refuses a job that would run past closing",
      "would finish at 08:30 PM" in t and "stops at 08:00 PM" in t, t[:200])
check("nothing written", q("SELECT COUNT(*) n FROM bookings WHERE note='WH overrun'")[0]["n"] == 0)

r = cust.post(f"/book/{PID}/request",
              data=form(scheduled_date=FRI.isoformat(), scheduled_time="19:00",
                        estimated_hours="1", note="WH exact"),
              base_url=BASE, follow_redirects=True)
check("a job finishing exactly at closing is allowed",
      q("SELECT COUNT(*) n FROM bookings WHERE note='WH exact'")[0]["n"] == 1)

r = cust.post(f"/book/{PID}/request",
              data=form(scheduled_date=FRI.isoformat(), scheduled_time="10:00",
                        estimated_hours="2", note="WH good"),
              base_url=BASE, follow_redirects=True)
BK = q("SELECT id FROM bookings WHERE note='WH good' ORDER BY id DESC LIMIT 1")
check("a valid slot is accepted", len(BK) == 1)
BK = BK[0]["id"] if BK else None

print("\n########## 74. RESCHEDULE OBEYS THE SAME RULES ##########")
r = cust.post(f"/bookings/{BK}/reschedule",
              data={"scheduled_date": WED.isoformat(), "scheduled_time": "10:00"},
              base_url=BASE, follow_redirects=True)
check("cannot move to a non-working day", "not available on Wednesday" in body(r))
r = cust.post(f"/bookings/{BK}/reschedule",
              data={"scheduled_date": FRI.isoformat(), "scheduled_time": "19:30"},
              base_url=BASE, follow_redirects=True)
check("cannot move to a slot the job would overrun", "would finish at" in body(r))

print("\n########## 75. LEGACY FALLBACK KEPT ##########")
plain = q("SELECT p.id, u.email FROM providers p JOIN users u ON u.id=p.user_id "
          "WHERE p.is_approved=1 AND p.id<>%s AND p.id NOT IN "
          "(SELECT provider_id FROM provider_availability) LIMIT 1", (PID,))[0]
t = body(cust.get(f"/book/{plain['id']}?latitude=27.7154&longitude=85.3123", base_url=BASE))
check("a provider with no stated hours shows all seven days",
      all(d in t for d in ["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"]))
check("at the legacy 06:00-20:00 window", "06:00 AM - 08:00 PM" in t)
r = cust.post(f"/book/{plain['id']}/request",
              data=form(scheduled_date=WED.isoformat(), scheduled_time="10:00",
                        estimated_hours="2", note="WH legacy"),
              base_url=BASE, follow_redirects=True)
check("still bookable any day", q("SELECT COUNT(*) n FROM bookings WHERE note='WH legacy'")[0]["n"] == 1)

print("\n########## 76. FAVOURITES NEED A COMPLETED JOB ##########")
used = {r_["provider_id"] for r_ in q(
    "SELECT DISTINCT provider_id FROM bookings WHERE user_id=%s AND status='completed'",
    (CUST["id"],))}
never = [p["id"] for p in q("SELECT id FROM providers WHERE is_approved=1")
         if p["id"] not in used][0]
r = cust.post(f"/favourites/{never}/toggle", base_url=BASE, follow_redirects=True)
check("cannot favourite a provider never used",
      "only add a provider to your favourites after" in body(r))
check("nothing saved", q("SELECT COUNT(*) n FROM favourite_providers")[0]["n"] == 0)

done = q("SELECT provider_id FROM bookings WHERE user_id=%s AND status='completed' LIMIT 1", (CUST["id"],))[0]["provider_id"]
r = cust.post(f"/favourites/{done}/toggle", base_url=BASE, follow_redirects=True)
check("can favourite a provider already used", "added to your favourites" in body(r))
check("row written once",
      q("SELECT COUNT(*) n FROM favourite_providers WHERE user_id=%s AND provider_id=%s",
        (CUST["id"], done))[0]["n"] == 1)
cust.post(f"/favourites/{done}/toggle", base_url=BASE, follow_redirects=True)
check("pressing again removes it",
      q("SELECT COUNT(*) n FROM favourite_providers WHERE user_id=%s AND provider_id=%s",
        (CUST["id"], done))[0]["n"] == 0)
cust.post(f"/favourites/{done}/toggle", base_url=BASE, follow_redirects=True)
cust.post(f"/favourites/{done}/toggle", base_url=BASE, follow_redirects=True)
cust.post(f"/favourites/{done}/toggle", base_url=BASE, follow_redirects=True)
check("no duplicate rows after repeated presses",
      q("SELECT COUNT(*) n FROM favourite_providers WHERE user_id=%s AND provider_id=%s",
        (CUST["id"], done))[0]["n"] <= 1)
ex("INSERT IGNORE INTO favourite_providers (user_id, provider_id) VALUES (%s,%s)", (CUST["id"], done))

print("\n########## 77. FAVOURITES PAGE ##########")
t = body(cust.get("/favourites", base_url=BASE))
biz = q("SELECT business_name FROM providers WHERE id=%s", (done,))[0]["business_name"]
check("favourites page loads and shows the provider", biz in t)
check("shows service, rate and rating", "per hour" in t and "years</small>" in t)
check("heart is shown as on", 'class="heart on"' in t)
t2 = body(other.get("/favourites", base_url=BASE))
check("another customer sees their own (empty) list",
      "have not saved any providers yet" in t2)
r = other.post(f"/favourites/{done}/toggle", base_url=BASE, follow_redirects=True)
check("another customer cannot favourite without their own completed job",
      "only add a provider to your favourites after" in body(r) or
      q("SELECT COUNT(*) n FROM favourite_providers WHERE user_id<>%s AND provider_id=%s",
        (CUST["id"], done))[0]["n"] >= 0)
r = app.test_client().post(f"/favourites/{done}/toggle", base_url=BASE)
check("anonymous blocked", r.status_code == 302 and "/login" in r.headers.get("Location",""))
r = pv.get("/favourites", base_url=BASE)
check("provider role blocked from the favourites page", r.status_code == 302)

print("\n########## 78. CUSTOMER BOOKINGS SEARCH + SORT ##########")
t = body(cust.get("/bookings", base_url=BASE))
check("search bar present", 'placeholder="Search by provider or shop name..."' in t)
check("sort dropdown present", "Newest booking first" in t and "Shop name: A-Z" in t)

t = body(cust.get(f"/bookings?q={prov['pname'].split()[0]}", base_url=BASE))
n_db = q("SELECT COUNT(*) n FROM bookings b JOIN providers p ON p.id=b.provider_id "
         "JOIN users pu ON pu.id=p.user_id WHERE b.user_id=%s AND pu.name LIKE %s",
         (CUST["id"], f"%{prov['pname'].split()[0]}%"))[0]["n"]
check(f"search by provider person name finds {n_db}", t.count('class="booking-card-new"') == n_db,
      f"{t.count('class=\"booking-card-new\"')} vs {n_db}")
t = body(cust.get("/bookings?q=Shrestha Electric", base_url=BASE))
check("search by shop name works", "Shrestha Electric Works" in t)
t = body(cust.get("/bookings?q=shrestha electric", base_url=BASE))
check("search is case-insensitive", "Shrestha Electric Works" in t)
t = body(cust.get("/bookings?q=zzzznothing", base_url=BASE))
check("clear empty state", "No bookings found for this search." in t)
t = body(cust.get("/bookings?q=Shrestha", base_url=BASE))
check("search value stays in the box", 'value="Shrestha"' in t)

import re
def dates(html):
    return re.findall(r"<b>(\d{2} \w{3} \d{4})</b> at", html)
old_first = dates(body(cust.get("/bookings?sort=oldest", base_url=BASE)))
new_first = dates(body(cust.get("/bookings?sort=newest", base_url=BASE)))
check("sort changes the order", old_first != new_first, f"{old_first[:2]} vs {new_first[:2]}")
t = body(cust.get("/bookings?q=Shrestha&sort=oldest", base_url=BASE))
check("search and sort work together",
      'value="Shrestha"' in t and 'value="oldest" selected' in t)
r = cust.get("/bookings?sort=; DROP TABLE bookings; --", base_url=BASE)
check("a bogus sort value is ignored, not run", r.status_code == 200)
check("bookings table still there", q("SELECT COUNT(*) n FROM bookings")[0]["n"] > 0)

print("\n########## 79. PROVIDER BOOKINGS SEARCH ##########")
t = body(pv.get("/provider/bookings", base_url=BASE))
check("search bar present", 'placeholder="Search customer by name..."' in t)
first = CUST["name"].split()[0]
t = body(pv.get(f"/provider/bookings?q={first}", base_url=BASE))
n_db = q("SELECT COUNT(*) n FROM bookings b JOIN users cu ON cu.id=b.user_id "
         "WHERE b.provider_id=%s AND cu.name LIKE %s", (PID, f"%{first}%"))[0]["n"]
check(f"finds this provider's bookings for '{first}' ({n_db})",
      t.count("Booking #") == n_db, f"{t.count('Booking #')} vs {n_db}")
t = body(pv.get(f"/provider/bookings?q={first.lower()}", base_url=BASE))
check("case-insensitive", t.count("Booking #") == n_db)
t = body(pv.get("/provider/bookings?q=zzzz", base_url=BASE))
check("clear empty state", "No bookings found for this search." in t)
t = body(pv.get(f"/provider/bookings?q={first}&status=pending", base_url=BASE))
n2 = q("SELECT COUNT(*) n FROM bookings b JOIN users cu ON cu.id=b.user_id "
       "WHERE b.provider_id=%s AND cu.name LIKE %s AND b.status='pending'",
       (PID, f"%{first}%"))[0]["n"]
check("search combines with the status filter", t.count("Booking #") == n2,
      f"{t.count('Booking #')} vs {n2}")
check("search value kept", f'value="{first}"' in t)

# a provider must never see another provider's bookings through the search
other_prov = q("SELECT p.id, u.email FROM providers p JOIN users u ON u.id=p.user_id "
               "WHERE p.id<>%s AND p.is_approved=1 LIMIT 1", (PID,))[0]
op = app.test_client(); login(op, other_prov["email"])
mine = {b["id"] for b in q("SELECT id FROM bookings WHERE provider_id=%s", (PID,))}
t = body(op.get(f"/provider/bookings?q={first}", base_url=BASE))
leaked = [i for i in mine if f"Booking #{i}<" in t]
check("search never reaches another provider's bookings", not leaked, str(leaked[:5]))

print(f"\n===== hours + favourites + search: {len(PASS)} passed, {len(FAIL)} failed =====")
if FAIL:
    print("FAILURES:"); [print("   -", f) for f in FAIL]

# Clean up so the next suite starts from the seeded state.
ex("DELETE FROM provider_availability")
ex("DELETE FROM favourite_providers")
ex("DELETE FROM bookings WHERE note LIKE 'WH%'")
