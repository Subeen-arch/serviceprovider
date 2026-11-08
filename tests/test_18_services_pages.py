"""Public pages: the homepage trade grid, All services, one service's page,
How it works and For providers.

Every number these pages show is compared with the database, so a template
can never quietly fall back to sample figures.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tests import support

support.use_test_database()

from app import app   # noqa: E402,F401  (imported after the database is chosen)
from algorithms.recommendation import DEFAULT_MODE, MODES   # noqa: E402

results = support.Results("services pages")
check = results.check
q, ex, body, BASE = support.q, support.ex, support.body, support.BASE

VISIBLE = ("p.is_approved = 1 AND p.is_available = 1 "
           "AND p.user_id IN (SELECT id FROM users WHERE is_active = 1)")

anon = support.client()

results.section("public pages render for a visitor")
for path in ("/", "/services", "/how-it-works", "/for-providers", "/contact"):
    r = anon.get(path, base_url=BASE)
    check(f"{path} renders", r.status_code == 200, str(r.status_code))

services = q("SELECT id, name FROM services WHERE is_active = 1 ORDER BY name")
check("sample data has services", len(services) > 0)

results.section("homepage trade grid")
t = body(anon.get("/", base_url=BASE))
check("one card per active service", t.count('class="svc-card"') == len(services),
      f"{t.count('class=\"svc-card\"')} vs {len(services)}")
check("cards open the service page",
      all(f'href="/services/{s["id"]}"' in t for s in services))
check("every card has a line icon", t.count('class="svc-icon"') >= len(services))
check("no hardcoded sample ranking left",
      "Shrestha Electric Works" not in t and "rank-92" not in t)
top = q("SELECT p.business_name FROM providers p JOIN services s ON s.id = p.service_id "
        "JOIN users u ON u.id = p.user_id "
        "LEFT JOIN (SELECT provider_id, AVG(rating) a, COUNT(*) n FROM reviews GROUP BY provider_id) r "
        "ON r.provider_id = p.id WHERE p.is_approved = 1 AND p.is_available = 1 "
        "AND u.is_active = 1 AND s.is_active = 1 "
        "ORDER BY (r.n IS NULL), r.a DESC, r.n DESC, p.experience_years DESC, p.id LIMIT 1")
check("preview is led by the real highest rated provider",
      bool(top) and top[0]["business_name"] in t)

results.section("All services")
t = body(anon.get("/services", base_url=BASE))
check("one row per active service", t.count('class="svc-row"') == len(services))
for s in services:
    n = q(f"SELECT COUNT(*) n FROM providers p WHERE p.service_id = %s AND {VISIBLE}",
          (s["id"],))[0]["n"]
    check(f"{s['name']}: count {n} matches the database",
          f'href="/services/{s["id"]}"' in t
          and f"<b>{n}</b>" in t.split(f'href="/services/{s["id"]}"', 1)[1][:900])

results.section("a deactivated account is not counted")
sid = services[0]["id"]
victim = q(f"SELECT p.user_id FROM providers p WHERE p.service_id = %s AND {VISIBLE} LIMIT 1",
           (sid,))
if victim:
    before = q(f"SELECT COUNT(*) n FROM providers p WHERE p.service_id = %s AND {VISIBLE}",
               (sid,))[0]["n"]
    ex("UPDATE users SET is_active = 0 WHERE id = %s", (victim[0]["user_id"],))
    try:
        t = body(anon.get(f"/services/{sid}", base_url=BASE))
        check("count drops by one", f"<b>{before - 1}</b> <span class=\"eyebrow\">approved provider" in t)
    finally:
        ex("UPDATE users SET is_active = 1 WHERE id = %s", (victim[0]["user_id"],))

results.section("one service's page")
t = body(anon.get(f"/services/{sid}", base_url=BASE))
check("back link to all services", 'href="/services"' in t)
check("visitor is asked to log in", "Log in to find one near me" in t)
weights = MODES[DEFAULT_MODE]["weights"]
check("ranking panel quotes the real weights",
      f"Distance &middot; {weights['distance']}" in t or f"Distance · {weights['distance']}" in t)
check("unknown service is a 404", anon.get("/services/999999", base_url=BASE).status_code == 404)
check("non-numeric id is a 404", anon.get("/services/abc", base_url=BASE).status_code == 404)
ex("UPDATE services SET is_active = 0 WHERE id = %s", (sid,))
try:
    check("inactive service is a 404", anon.get(f"/services/{sid}", base_url=BASE).status_code == 404)
finally:
    ex("UPDATE services SET is_active = 1 WHERE id = %s", (sid,))

results.section("the button depends on who is looking")
cust = support.client(support.CUSTOMER_EMAIL)
t = body(cust.get(f"/services/{sid}", base_url=BASE))
check("customer gets a search for this service", f"/search?service_id={sid}" in t)
prov = support.client(support.PROVIDER_EMAIL)
t = body(prov.get(f"/services/{sid}", base_url=BASE))
check("provider gets no booking button", "find one near me" not in t.lower())

results.section("provider sign-up shortcut")
t = body(anon.get("/register?role=provider", base_url=BASE))
check("register?role=provider preselects provider",
      'value="provider" checked' in t or 'value="provider" selected' in t)

results.section("search text is escaped")
t = body(anon.get("/services?q=<script>alert(1)</script>", base_url=BASE))
check("no script injected", "<script>alert(1)</script>" not in t)

raise SystemExit(1 if results.report() else 0)
