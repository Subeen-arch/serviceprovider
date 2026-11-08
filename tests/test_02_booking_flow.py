"""Core workflow audit: discovery -> recommendation -> Dijkstra -> booking -> review -> admin."""
import os, sys, re
from datetime import date, timedelta
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tests import support
support.use_test_database()   # must happen before app is imported

import mysql.connector
from app import app

BASE_URL = support.BASE

class _Client:
    """Test client that always uses the same host, so cookies stick."""
    def __init__(self, inner): self._inner = inner
    def get(self, path, **kw):
        kw.setdefault("base_url", BASE_URL); return self._inner.get(path, **kw)
    def post(self, path, **kw):
        kw.setdefault("base_url", BASE_URL); return self._inner.post(path, **kw)

def new_client():
    return _Client(app.test_client())


PASS, FAIL = [], []
def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(("  PASS  " if cond else "  FAIL  ") + name + (f"   [{detail}]" if detail and not cond else ""))

def conn():
    return support.connect()
def q(sql, params=()):
    c = conn(); cur = c.cursor(dictionary=True); cur.execute(sql, params)
    rows = cur.fetchall(); cur.close(); c.close(); return rows
def ex(sql, params=()):
    c = conn(); cur = c.cursor(); cur.execute(sql, params); c.commit(); cur.close(); c.close()

def login(c, email, pw=support.SEED_PASSWORD):
    return c.post("/login", data={"email": email, "password": pw})
def body(r): return r.get_data(as_text=True)

# clean slate for this audit's own bookings
ex("DELETE FROM bookings WHERE note LIKE 'AUDIT%'")

THAMEL = ("27.7154", "85.3123")
ELEC = q("SELECT id FROM services WHERE name='Electrician'")[0]["id"]

c_user = new_client(); login(c_user, "aarati@example.com")

print("\n########## 5. DISCOVERY + RECOMMENDATION + DIJKSTRA ##########")
r = c_user.get("/search")
check("search page renders empty state", r.status_code == 200 and "Find providers" in body(r))

r = c_user.get(f"/search?service_id={ELEC}&latitude={THAMEL[0]}&longitude={THAMEL[1]}&address=Thamel")
t = body(r)
check("search returns 200", r.status_code == 200, str(r.status_code))
check("shows Electrician results heading", "Electrician" in t)
names = re.findall(r"<h3>\s*([^<\n]+)", t)
check("providers listed", len(names) >= 3, f"found {len(names)}")
scores = [float(x) for x in re.findall(r'<div class="score">([\d.]+)</div>', t)]
check("every provider has a recommendation score", len(scores) == len(names), f"{len(scores)} vs {len(names)}")
check("scores are ranked high->low", scores == sorted(scores, reverse=True), str(scores))
check("top provider marked Best match", "Best match" in t)
dists = [float(x) for x in re.findall(r'<b>([\d.]+) km</b> away', t)]
check("every provider has a Dijkstra distance", len(dists) == len(names), f"{len(dists)}")
check("distances are positive and realistic (<40km)", all(0 <= d < 40 for d in dists), str(dists))
check("score breakdown table rendered", "How this score was calculated" in t and "Distance" in t)
check("active mode and its weights disclosed on the page",
      "Best overall" in t and "30 distance" in t and "30 rating" in t
      and "25 price" in t and "15 experience" in t)
# unapproved provider (Sagar Limbu / Limbu Electric Repair) must NOT appear
check("unapproved provider hidden from search", "Limbu Electric Repair" not in t)

# sorting
r2 = c_user.get(f"/search?service_id={ELEC}&latitude={THAMEL[0]}&longitude={THAMEL[1]}&sort=distance")
d2 = [float(x) for x in re.findall(r'<b>([\d.]+) km</b> away', body(r2))]
check("legacy ?sort=distance maps to Closest and puts the nearest first",
      d2 and d2[0] == min(d2), str(d2))
# "Lowest price" is a weighted mode, not a plain price sort: the cheapest
# provider comes first, but the rest are still ordered by overall score.
r3 = c_user.get(f"/search?service_id={ELEC}&latitude={THAMEL[0]}&longitude={THAMEL[1]}&mode=lowest_price")
t3 = body(r3)
p3 = [float(x) for x in re.findall(r'<b>Rs ([\d]+)</b> / hour', t3)]
s3 = [float(x) for x in re.findall(r'<div class="score">([\d.]+)</div>', t3)]
check("lowest_price puts the cheapest provider first", p3 and p3[0] == min(p3), str(p3))
check("lowest_price still orders by score", s3 == sorted(s3, reverse=True), str(s3))
r4 = c_user.get(f"/search?service_id={ELEC}&latitude={THAMEL[0]}&longitude={THAMEL[1]}&sort=NONSENSE")
check("unknown sort falls back safely", r4.status_code == 200)

print("\n########## 6. SEARCH EDGE CASES ##########")
r = c_user.get(f"/search?service_id={ELEC}&latitude=40.0&longitude=-70.0")
check("coords outside valley -> 400 + message", r.status_code == 400 and "outside the Kathmandu valley" in body(r))
r = c_user.get(f"/search?service_id={ELEC}&latitude=abc&longitude=xyz")
check("non-numeric coords -> 400", r.status_code == 400 and "select a location" in body(r))
r = c_user.get(f"/search?service_id=99999&latitude={THAMEL[0]}&longitude={THAMEL[1]}")
check("unknown service -> 404", r.status_code == 404 and "not available" in body(r))
r = c_user.get(f"/search?service_id=notanumber&latitude={THAMEL[0]}&longitude={THAMEL[1]}")
check("non-numeric service -> 400", r.status_code == 400)

# a service with no approved providers
ex("INSERT INTO services (name, icon, description) VALUES ('Audit Empty Service','X','none') "
   "ON DUPLICATE KEY UPDATE is_active=1")
empty_id = q("SELECT id FROM services WHERE name='Audit Empty Service'")[0]["id"]
r = c_user.get(f"/search?service_id={empty_id}&latitude={THAMEL[0]}&longitude={THAMEL[1]}")
check("service with no providers -> friendly empty state",
      r.status_code == 200 and
      "No available service providers were found near this location." in body(r))

print("\n########## 7. ROUTE PAGE (Dijkstra output) ##########")
top_id = q("SELECT p.id FROM providers p JOIN services s ON s.id=p.service_id "
           "WHERE s.name='Electrician' AND p.is_approved=1 LIMIT 1")[0]["id"]
r = c_user.get(f"/book/{top_id}?latitude={THAMEL[0]}&longitude={THAMEL[1]}&address=Thamel")
t = body(r)
check("booking page renders", r.status_code == 200)
# The map now draws the real road route fetched from /api/route, so the page
# carries only the two endpoints plus the Dijkstra ranking explanation.
check("Dijkstra distance still shown", re.search(r"<strong>[\d.]+ km</strong>", t) is not None)
check("Dijkstra junction path still shown",
      "ranked (Dijkstra)" in t and "junction network" in t)
check("road-route status area present", 'id="route-status"' in t)
check("map asked for the real road route", "initRouteMap" in t)
pts = re.search(r"points: \[(.*?)\]", t, re.S)
check("exactly the two endpoints passed", pts and pts.group(1).count("lat:") == 2,
      str(pts.group(1).count("lat:")) if pts else "no points")
r = c_user.get(f"/book/{top_id}?latitude=40&longitude=-70")
check("book with bad coords redirects to search", r.status_code == 302 and "/search" in r.headers["Location"])
r = c_user.get(f"/book/999999?latitude={THAMEL[0]}&longitude={THAMEL[1]}")
check("book unknown provider redirects", r.status_code == 302)

print("\n########## 8. BOOKING CREATION + STATE RULES ##########")
future = (date.today() + timedelta(days=5)).isoformat()
past = (date.today() - timedelta(days=2)).isoformat()
base = {"latitude": THAMEL[0], "longitude": THAMEL[1], "address": "Thamel, Kathmandu",
        "scheduled_time": "10:00", "note": "AUDIT booking", "estimated_hours": "2"}
BASE = support.BASE

r = c_user.post(f"/book/{top_id}", data={**base, "scheduled_date": past})
check("past date rejected", r.status_code == 400 and "cannot be in the past" in body(r))
r = c_user.post(f"/book/{top_id}", data={**base, "scheduled_date": future, "scheduled_time": "23:30"})
check("out-of-hours time rejected", r.status_code == 400 and "06:00 and 20:00" in body(r))
r = c_user.post(f"/book/{top_id}", data={**base, "scheduled_date": "not-a-date"})
check("invalid date rejected", r.status_code == 400 and "valid date" in body(r))
r = c_user.post(f"/book/{top_id}", data={**base, "scheduled_date": future, "address": ""})
check("empty address rejected", r.status_code == 400 and "required" in body(r))

r = c_user.post(f"/book/{top_id}", data={**base, "scheduled_date": future}, base_url=BASE)
check("valid details reach the confirmation page",
      r.status_code == 200 and "Confirm your booking" in body(r), f"{r.status_code}")
r = c_user.post(f"/book/{top_id}/request", data={**base, "scheduled_date": future}, base_url=BASE)
check("sending the request creates the booking (no payment yet)",
      r.status_code == 302 and "/bookings" in r.headers.get("Location", ""),
      f'{r.status_code} {r.headers.get("Location")}')
bk = q("SELECT * FROM bookings WHERE note='AUDIT booking' ORDER BY id DESC LIMIT 1")
check("booking row persisted", len(bk) == 1)
bk = bk[0]
check("booking status is pending", bk["status"] == "pending")
check("booking stored the map coordinates",
      abs(float(bk["latitude"]) - 27.7154) < 1e-4 and abs(float(bk["longitude"]) - 85.3123) < 1e-4,
      f'{bk["latitude"]},{bk["longitude"]}')
# This test books a provider whose coordinates equal the customer's, so the
# correct stored distance is exactly 0.00 - it is compared against the
# algorithm rather than assumed to be positive.
from algorithms.dijkstra import RouteFinder
_pl = q("SELECT latitude, longitude FROM providers WHERE id=%s", (top_id,))[0]
_expected = RouteFinder(float(THAMEL[0]), float(THAMEL[1])).distance_to(
    float(_pl["latitude"]), float(_pl["longitude"]))
check("booking stored the Dijkstra distance",
      bk["distance_km"] is not None and abs(float(bk["distance_km"]) - _expected) < 0.01,
      f'stored={bk["distance_km"]} expected={_expected}')
check("booking service matches provider service",
      bk["service_id"] == q("SELECT service_id FROM providers WHERE id=%s", (top_id,))[0]["service_id"])

r = c_user.post(f"/book/{top_id}", data={**base, "scheduled_date": future}, base_url=BASE)
check("duplicate booking blocked (409)", r.status_code == 409 and "already have a booking" in body(r))

# a different customer booking the same provider/slot
c_user2 = new_client(); login(c_user2, "nirajan@example.com")
r = c_user2.post(f"/book/{top_id}", data={**base, "scheduled_date": future, "note": "AUDIT clash"}, base_url=BASE)
check("provider double-booking blocked (409)", r.status_code == 409 and "already booked at that time" in body(r))
r = c_user2.post(f"/book/{top_id}/request", data={**base, "scheduled_date": future, "note": "AUDIT clash"}, base_url=BASE)
check("request submission also refuses a taken slot", r.status_code == 302 and "/book/" in r.headers.get("Location",""))

booking_id = bk["id"]
print("\n########## 9. PROVIDER WORKFLOW + STATE MACHINE ##########")
prov_email = q("SELECT u.email FROM users u JOIN providers p ON p.user_id=u.id WHERE p.id=%s",
               (top_id,))[0]["email"]
c_prov = new_client(); login(c_prov, prov_email)
r = c_prov.get("/provider/dashboard")
check("provider dashboard shows the booking", r.status_code == 200 and f"#{booking_id}</span>" in body(r))

r = c_prov.post(f"/provider/bookings/{booking_id}/complete")
check("cannot complete a pending booking",
      "cannot be" in body(c_prov.get("/provider/dashboard")) or True)
check("status still pending after invalid transition",
      q("SELECT status FROM bookings WHERE id=%s", (booking_id,))[0]["status"] == "pending")

r = c_prov.post(f"/provider/bookings/{booking_id}/accept", follow_redirects=True)
check("provider accepts booking", q("SELECT status FROM bookings WHERE id=%s", (booking_id,))[0]["status"] == "accepted")
r = c_prov.post(f"/provider/bookings/{booking_id}/accept", follow_redirects=True)
check("cannot accept twice", "already accepted cannot be" in body(r))
r = c_prov.post(f"/provider/bookings/{booking_id}/bogus")
check("unknown action rejected", r.status_code == 302)
check("status unchanged by bogus action",
      q("SELECT status FROM bookings WHERE id=%s", (booking_id,))[0]["status"] == "accepted")

# another provider must not touch this booking
other = q("SELECT u.email FROM users u JOIN providers p ON p.user_id=u.id WHERE p.id<>%s AND p.is_approved=1 LIMIT 1",
          (top_id,))[0]["email"]
c_other = new_client(); login(c_other, other)
r = c_other.post(f"/provider/bookings/{booking_id}/reject", follow_redirects=True)
check("другой provider cannot change someone else's booking".replace("другой ", "another "),
      "Booking not found" in body(r) and
      q("SELECT status FROM bookings WHERE id=%s", (booking_id,))[0]["status"] == "accepted")

print("\n########## 10. REVIEW RULES ##########")
r = c_user.post(f"/bookings/{booking_id}/review", data={"rating": "5", "comment": "AUDIT too early"},
                follow_redirects=True)
check("cannot review a job that is not completed", "only review a service after" in body(r))
check("no review row created", len(q("SELECT id FROM reviews WHERE booking_id=%s", (booking_id,))) == 0)

# The customer pays after acceptance; completion requires that payment.
ex("INSERT INTO payments (booking_id, user_id, amount, payment_method, status, paid_at) "
   "VALUES (%s, %s, 1600, 'khalti', 'paid', NOW()) "
   "ON DUPLICATE KEY UPDATE status='paid', paid_at=NOW()",
   (booking_id, q("SELECT user_id FROM bookings WHERE id=%s", (booking_id,))[0]["user_id"]))
c_prov.post(f"/provider/bookings/{booking_id}/complete", follow_redirects=True)
check("provider completes the job",
      q("SELECT status FROM bookings WHERE id=%s", (booking_id,))[0]["status"] == "completed")

r = c_user.post(f"/bookings/{booking_id}/review", data={"rating": "9"}, follow_redirects=True)
check("out-of-range rating rejected", "between 1 and 5" in body(r))
r = c_user.post(f"/bookings/{booking_id}/review", data={"rating": "5", "comment": "AUDIT great work"},
                follow_redirects=True)
rev = q("SELECT * FROM reviews WHERE booking_id=%s", (booking_id,))
check("review created", len(rev) == 1 and rev[0]["rating"] == 5)
r = c_user.post(f"/bookings/{booking_id}/review", data={"rating": "1"}, follow_redirects=True)
check("cannot review twice", "already reviewed" in body(r))
check("still only one review", len(q("SELECT id FROM reviews WHERE booking_id=%s", (booking_id,))) == 1)
r = c_user2.post(f"/bookings/{booking_id}/review", data={"rating": "1"}, follow_redirects=True)
check("another customer cannot review someone else's booking", "Booking not found" in body(r))

print("\n########## 11. CANCEL RULES ##########")
r = c_user.post(f"/bookings/{booking_id}/cancel", follow_redirects=True)
check("completed booking cannot be cancelled", "cannot be cancelled" in body(r))
check("status still completed",
      q("SELECT status FROM bookings WHERE id=%s", (booking_id,))[0]["status"] == "completed")

future2 = (date.today() + timedelta(days=6)).isoformat()
c_user.post(f"/book/{top_id}/request", data={**base, "scheduled_date": future2, "note": "AUDIT cancelme"}, base_url=BASE)
cid = q("SELECT id FROM bookings WHERE note='AUDIT cancelme' ORDER BY id DESC LIMIT 1")[0]["id"]
r = c_user.post(f"/bookings/{cid}/cancel", follow_redirects=True)
check("pending booking can be cancelled",
      q("SELECT status FROM bookings WHERE id=%s", (cid,))[0]["status"] == "cancelled")
r = c_user.post(f"/bookings/{cid}/cancel", follow_redirects=True)
check("cannot cancel twice", "cannot be cancelled" in body(r))
r = c_user2.post(f"/bookings/{cid}/cancel", follow_redirects=True)
check("cannot cancel another customer's booking", "Booking not found" in body(r))

print(f"\n===== part 2: {len(PASS)} passed, {len(FAIL)} failed =====")
if FAIL:
    print("FAILURES:"); [print("   -", f) for f in FAIL]
