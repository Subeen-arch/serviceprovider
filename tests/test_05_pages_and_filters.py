"""Acceptance tests for the new work: rename, clickable cards, filters,
password change, real road routing, and access control on every new route."""
import os, sys, re
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tests import support
support.use_test_database()   # must happen before app is imported

import mysql.connector
from app import app

BASE = support.BASE
class _C:
    def __init__(self, i): self._i = i
    def get(self, p, **k): k.setdefault("base_url", BASE); return self._i.get(p, **k)
    def post(self, p, **k): k.setdefault("base_url", BASE); return self._i.post(p, **k)
def new_client(): return _C(app.test_client())

PASS, FAIL = [], []
def check(n, c, d=""):
    (PASS if c else FAIL).append(n)
    print(("  PASS  " if c else "  FAIL  ") + n + (f"   [{d}]" if d and not c else ""))
def q(sql, p=()):
    c = support.connect()
    cur = c.cursor(dictionary=True); cur.execute(sql, p)
    r = cur.fetchall(); cur.close(); c.close(); return r
def login(c, e, pw=support.SEED_PASSWORD): return c.post("/login", data={"email": e, "password": pw})
def body(r): return r.get_data(as_text=True)

admin = new_client(); login(admin, "admin@serviceexpert.local")
cust  = new_client(); login(cust,  "aarati@example.com")
prov  = new_client(); login(prov,  "ramesh.s@example.com")

print("\n########## 28. RENAME ##########")
for path, cl in [("/", new_client()), ("/login", new_client()), ("/admin/dashboard", admin),
                 ("/search", cust), ("/provider/dashboard", prov)]:
    t = body(cl.get(path))
    check(f"no 'Service Expert' on {path}", "Service Expert" not in t)
check("brand shows 'Service Provider'", "Service Provider" in body(new_client().get("/")))

print("\n########## 29. ADMIN OVERVIEW CARDS ARE REAL LINKS ##########")
t = body(admin.get("/admin/dashboard"))
expected = {
    "Customers":          "/admin/users?role=user",
    "Provider accounts":  "/admin/providers",
    "Active services":    "/admin/services",
    "Total bookings":     "/admin/bookings",
    "Reviews submitted":  "/admin/reviews",
    "Collected from":     "/admin/payments?status=paid",
    "Waiting for approval": "/admin/providers?status=pending",
}
# Split on each card's opening tag so one card's label cannot bleed into the next.
cards = []
for m in re.finditer(r'<a class="stat" href="([^"]+)">', t):
    inner = t[m.end():t.find("</a>", m.end())]
    cards.append((" ".join(re.sub(r"<[^>]+>", " ", inner).split()), m.group(1)))
check("all 7 overview cards render", len(cards) == 7, str(len(cards)))
for label, href in expected.items():
    found = [h for lbl, h in cards if label in lbl]
    check(f"'{label}' card is an <a> to {href}", found and found[0] == href,
          str(found))
check("no onclick divs used for cards", "onclick" not in t.split("Bookings by status")[0])

for status in ["pending", "accepted", "rejected", "completed", "cancelled"]:
    check(f"status card '{status}' links to filtered bookings",
          f'href="/admin/bookings?status={status}"' in t)

print("\n########## 30. ADMIN LINK TARGETS ACTUALLY WORK ##########")
for href in ["/admin/users?role=user", "/admin/providers", "/admin/services",
             "/admin/bookings", "/admin/reviews", "/admin/payments?status=paid",
             "/admin/providers?status=pending"]:
    r = admin.get(href)
    check(f"GET {href} -> 200", r.status_code == 200, str(r.status_code))

only_users = q("SELECT COUNT(*) n FROM users WHERE role='user'")[0]["n"]
t = body(admin.get("/admin/users?role=user"))
check("?role=user really filters", t.count('badge-muted">user') == only_users,
      f"html={t.count('badge-muted>user')} db={only_users}")
pending_n = q("SELECT COUNT(*) n FROM providers WHERE is_approved=0")[0]["n"]
t = body(admin.get("/admin/providers?status=pending"))
check("?status=pending really filters", t.count("badge-pending") == pending_n,
      f"html={t.count('badge-pending')} db={pending_n}")

print("\n########## 31. MOST BOOKED SERVICES -> SERVICE-FILTERED BOOKINGS ##########")
t = body(admin.get("/admin/dashboard"))
svc = q("SELECT s.id, s.name FROM services s JOIN bookings b ON b.service_id=s.id "
        "GROUP BY s.id ORDER BY COUNT(b.id) DESC LIMIT 1")[0]
check(f"'{svc['name']}' row links by service_id",
      f'href="/admin/bookings?service_id={svc["id"]}"' in t)
r = admin.get(f"/admin/bookings?service_id={svc['id']}")
t = body(r)
n_db = q("SELECT COUNT(*) n FROM bookings WHERE service_id=%s", (svc["id"],))[0]["n"]
check("service filter page loads", r.status_code == 200)
check(f"only {svc['name']} bookings shown ({n_db})", t.count("row-link") == n_db,
      f"rows={t.count('row-link')} db={n_db}")
check("heading names the service", svc["name"] in t)
r = admin.get(f"/admin/bookings?service_id={svc['id']}&status=completed")
n2 = q("SELECT COUNT(*) n FROM bookings WHERE service_id=%s AND status='completed'", (svc["id"],))[0]["n"]
check("service + status filters combine", body(r).count("row-link") == n2,
      f"rows={body(r).count('row-link')} db={n2}")
r = admin.get("/admin/bookings?service_id=99999")
check("unknown service_id falls back safely", r.status_code == 200)
r = admin.get("/admin/bookings?service_id=abc")
check("non-numeric service_id handled", r.status_code == 200)

print("\n########## 32. ADMIN BOOKING DETAIL + VIEW ALL ##########")
bid = q("SELECT id FROM bookings ORDER BY id DESC LIMIT 1")[0]["id"]
r = admin.get(f"/admin/bookings/{bid}")
t = body(r)
check("booking detail loads", r.status_code == 200 and f"Booking #{bid}" in t)
check("detail shows customer, provider and payment", "Customer" in t and "Provider" in t and "Payment" in t)
r = admin.get("/admin/bookings/999999", follow_redirects=True)
check("unknown booking handled", "Booking not found" in body(r))
check("'View all' points at the bookings page",
      'href="/admin/bookings"' in body(admin.get("/admin/dashboard")))

print("\n########## 33. ADMIN REVIEWS + PAYMENTS FROM THE DATABASE ##########")
t = body(admin.get("/admin/reviews"))
n_rev = q("SELECT COUNT(*) n FROM reviews")[0]["n"]
check("reviews page lists every review", t.count("row-link") == n_rev, f"{t.count('row-link')} vs {n_rev}")
avg = q("SELECT AVG(rating) a FROM reviews")[0]["a"]
check("average rating shown from DB", f"{float(avg):.1f}" in t, f"{float(avg):.1f}")

paid = q("SELECT COUNT(*) n, COALESCE(SUM(amount),0) t FROM payments WHERE status='paid'")[0]
t = body(admin.get("/admin/payments?status=paid"))
check("payments page lists paid rows", t.count("row-link") == paid["n"], f"{t.count('row-link')} vs {paid['n']}")
check("paid total matches DB", f"Rs {float(paid['t']):.0f}" in t, f"Rs {float(paid['t']):.0f}")
r = admin.get("/admin/payments?status=BOGUS")
check("invalid payment status falls back", r.status_code == 200)

print("\n########## 34. PROVIDER DASHBOARD CARDS + FILTERS ##########")
t = body(prov.get("/provider/dashboard"))
for label, href in [("Waiting for your reply", "/provider/bookings?status=pending"),
                    ("Accepted jobs", "/provider/bookings?status=accepted"),
                    ("Completed jobs", "/provider/bookings?status=completed")]:
    check(f"'{label}' card links to {href}", f'href="{href}"' in t)
check("rating card links to reviews", 'href="/provider/reviews"' in t)

me = q("SELECT p.id FROM providers p JOIN users u ON u.id=p.user_id "
       "WHERE u.email='ramesh.s@example.com'")[0]["id"]
for status in ["pending", "accepted", "completed"]:
    r = prov.get(f"/provider/bookings?status={status}")
    n = q("SELECT COUNT(*) n FROM bookings WHERE provider_id=%s AND status=%s", (me, status))[0]["n"]
    check(f"provider filter '{status}' matches DB ({n})",
          r.status_code == 200 and body(r).count(f'badge-{status}">{status}') == n,
          f"{body(r).count(chr(34)+'badge-'+status)} vs {n}")
r = prov.get("/provider/reviews")
n = q("SELECT COUNT(*) n FROM reviews WHERE provider_id=%s", (me,))[0]["n"]
check("provider reviews page loads", r.status_code == 200)
check("shows only this provider's reviews", body(r).count('class="review"') == n,
      f"{body(r).count(chr(34)+'review'+chr(34))} vs {n}")

print("\n########## 35. PROVIDER ONLY SEES ITS OWN DATA ##########")
other_email = q("SELECT u.email FROM users u JOIN providers p ON p.user_id=u.id "
                "WHERE p.id<>%s AND p.is_approved=1 LIMIT 1", (me,))[0]["email"]
other = new_client(); login(other, other_email)
mine = {b["id"] for b in q("SELECT id FROM bookings WHERE provider_id=%s", (me,))}
t = body(other.get("/provider/bookings"))
leaked = [i for i in mine if f"Booking #{i}" in t]
check("another provider cannot see my bookings", not leaked, str(leaked[:5]))
t = body(other.get("/provider/reviews"))
check("another provider's review page differs", t != body(prov.get("/provider/reviews")))

print("\n########## 36. ACCESS CONTROL ON NEW ROUTES ##########")
anon = new_client()
for path in ["/admin/reviews", "/admin/payments", f"/admin/bookings/{bid}",
             "/provider/bookings", "/provider/reviews", "/api/route?srcLat=27.7&srcLng=85.3&dstLat=27.6&dstLng=85.3"]:
    r = anon.get(path)
    check(f"anon blocked from {path.split('?')[0]}",
          r.status_code == 302 and "/login" in r.headers.get("Location", ""), str(r.status_code))
r = anon.post("/profile/password")
check("anon blocked from password change", r.status_code == 302 and "/login" in r.headers.get("Location",""))
for path in ["/admin/reviews", "/admin/payments", f"/admin/bookings/{bid}"]:
    r = cust.get(path)
    check(f"customer blocked from {path}", r.status_code == 302 and not r.headers.get("Location","").endswith(path))
    r = prov.get(path)
    check(f"provider blocked from {path}", r.status_code == 302 and not r.headers.get("Location","").endswith(path))
for path in ["/provider/bookings", "/provider/reviews"]:
    r = cust.get(path)
    check(f"customer blocked from {path}", r.status_code == 302 and not r.headers.get("Location","").endswith(path))
r = admin.get("/provider/bookings")
check("admin blocked from provider bookings", r.status_code == 302)

print("\n########## 37. PASSWORD CHANGE (all three roles) ##########")
import auth as auth_mod
def pw_hash(email):
    return q("SELECT password_hash FROM users WHERE email=%s", (email,))[0]["password_hash"]

for role, cl, email in [("customer", cust, "aarati@example.com"),
                        ("provider", prov, "ramesh.s@example.com"),
                        ("admin",    admin, "admin@serviceexpert.local")]:
    t = body(cl.get("/profile"))
    check(f"{role} sees the change-password form", "Change password" in t and "current_password" in t)

    before = pw_hash(email)
    r = cl.post("/profile/password", data={"current_password": "WRONGpass1",
                "new_password": "Newpass123", "confirm_password": "Newpass123"},
                follow_redirects=True)
    check(f"{role}: wrong current password rejected", "current password is not correct" in body(r))
    check(f"{role}: hash unchanged after wrong password", pw_hash(email) == before)

    r = cl.post("/profile/password", data={"current_password": support.SEED_PASSWORD,
                "new_password": "Newpass123", "confirm_password": "Different123"},
                follow_redirects=True)
    check(f"{role}: mismatch rejected", "do not match" in body(r))
    check(f"{role}: hash unchanged after mismatch", pw_hash(email) == before)

    r = cl.post("/profile/password", data={"current_password": support.SEED_PASSWORD,
                "new_password": "short", "confirm_password": "short"}, follow_redirects=True)
    check(f"{role}: short password rejected", "at least 8 characters" in body(r))

    r = cl.post("/profile/password", data={"current_password": support.SEED_PASSWORD,
                "new_password": support.SEED_PASSWORD, "confirm_password": support.SEED_PASSWORD}, follow_redirects=True)
    check(f"{role}: reusing the same password rejected", "must be different" in body(r))

    r = cl.post("/profile/password", data={"current_password": support.SEED_PASSWORD,
                "new_password": "Newpass123", "confirm_password": "Newpass123"},
                follow_redirects=True)
    after = pw_hash(email)
    check(f"{role}: password changed", "password has been changed" in body(r) and after != before)
    check(f"{role}: stored as a hash, not plaintext",
          "Newpass123" not in after and len(after) > 40)
    check(f"{role}: new password verifies", auth_mod.verify_password(after, "Newpass123"))
    check(f"{role}: still logged in after the change", cl.get("/profile").status_code == 200)
    fresh = new_client()
    check(f"{role}: can log in with the new password",
          login(fresh, email, "Newpass123").status_code == 302)
    check(f"{role}: old password no longer works",
          login(new_client(), email, support.SEED_PASSWORD).status_code == 401)
    check(f"{role}: hash never rendered in the page", after not in body(cl.get("/profile")))
    # restore
    cl.post("/profile/password", data={"current_password": "Newpass123",
            "new_password": support.SEED_PASSWORD, "confirm_password": support.SEED_PASSWORD}, follow_redirects=True)

print("\n########## 38. REAL ROAD ROUTE (live routing engine) ##########")
r = cust.get("/api/route?srcLat=27.7154&srcLng=85.3123&dstLat=27.6582&dstLng=85.3252")
d = r.get_json()
check("route API returns 200", r.status_code == 200, str(r.status_code))
check("ok with distance and duration", d and d.get("ok") and d["distance_km"] > 0 and d["duration_min"] > 0,
      str(d)[:120])
check("many points -> follows roads, not a straight line", d and len(d["points"]) > 50,
      str(len(d.get("points", []))))
if d and d.get("ok"):
    pts = d["points"]
    straight = [[27.7154, 85.3123], [27.6582, 85.3252]]
    check("geometry is not just the two endpoints", pts != straight)
    print(f"        -> {d['distance_km']} km, {d['duration_min']} min, {len(pts)} road points")
check("Galli token not leaked in the JSON", "f2095659" not in body(r))
r = cust.get("/api/route?srcLat=99&srcLng=999&dstLat=27.6&dstLng=85.3")
check("invalid coords -> 400", r.status_code == 400 and r.get_json()["ok"] is False)
r = cust.get("/api/route?srcLat=abc&srcLng=def&dstLat=27.6&dstLng=85.3")
check("non-numeric coords -> 400", r.status_code == 400)

print("\n########## 39. NO STRAIGHT-LINE ROUTE LEFT IN THE JS ##########")
import pathlib
js = pathlib.Path(r"c:\Service_provider\static\js\galli-map.js").read_text(encoding="utf-8")
check("route geometry comes from /api/route", "/api/route" in js)
check("no straight two-point polyline built from config.points",
      "config.points.map" not in js)
check("failure never falls back to a line",
      "Road route unavailable" in js and "straight line" in js.lower())
t = body(cust.get(f"/book/{me}?latitude=27.6582&longitude=85.3252&address=Satdobato"))
check("booking page asks for the real route", "initRouteMap" in t and "route-status" in t)
check("booking page no longer inlines junction geometry as the route",
      '"name": "Ratna Park"' not in t and "dijkstra-route" not in t)
check("Dijkstra ranking still explained on the page", "Dijkstra" in t and "junction" in t)

print("\n########## 40. SEARCH: INLINE RESULTS, SCROLL, LOADING ##########")
elec = q("SELECT id FROM services WHERE name='Electrician'")[0]["id"]
t = body(cust.get(f"/search?service_id={elec}&latitude=27.7154&longitude=85.3123&address=Thamel"))
check("results render inline with an anchor", 'id="results"' in t)
check("smooth scroll runs only after a search", 'behavior: "smooth"' in t and "scrollIntoView" in t)
check("no modal/dialog used", "<dialog" not in t and "modal" not in t.lower())
check("loading state on the button", 'id="find-btn"' in t and "Searching" in t)
check("double submit guarded", "submitting" in t)
t2 = body(cust.get("/search"))
check("no scroll script before a search has run", "scrollIntoView" not in t2)
empty = q("SELECT id FROM services WHERE id NOT IN (SELECT service_id FROM providers) LIMIT 1")
if empty:
    t3 = body(cust.get(f"/search?service_id={empty[0]['id']}&latitude=27.7154&longitude=85.3123"))
    check("no-provider message is the requested wording",
          "No available service providers were found near this location." in t3)

print("\n########## 41. PAYMENT PROVIDER NAME IS DYNAMIC ##########")
src = pathlib.Path(r"c:\Service_provider\routes\user_routes.py").read_text(encoding="utf-8")
check("no hard-coded shop name anywhere", "SportHub" not in src)
check("order name falls back to 'Service Provider'", '"Service Provider"' in src)
check("order name comes from the provider record", "business_name = (provider_name" in src)
t = body(cust.get(f"/book/{me}?latitude=27.7154&longitude=85.3123&address=Thamel"))
biz = q("SELECT business_name FROM providers WHERE id=%s", (me,))[0]["business_name"]
check("booking page shows the real business name", biz in t, biz)

print(f"\n===== new work: {len(PASS)} passed, {len(FAIL)} failed =====")
if FAIL:
    print("FAILURES:"); [print("   -", f) for f in FAIL]
