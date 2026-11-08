"""Admin operations, profile editing, deactivation effects, live map API, error pages."""
import os, sys, re, json
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
def login(c, email, pw=support.SEED_PASSWORD): return c.post("/login", data={"email": email, "password": pw})
def body(r): return r.get_data(as_text=True)

ex("DELETE FROM bookings WHERE note LIKE 'AUDIT3%'")
ex("DELETE FROM services WHERE name IN ('Audit New Service')")

c_admin = new_client(); login(c_admin, "admin@serviceexpert.local")
c_user  = new_client(); login(c_user,  "aarati@example.com")

print("\n########## 12. DIJKSTRA DISTANCE PERSISTED (far origin) ##########")
SATDOBATO = ("27.6582", "85.3252")
elec = q("SELECT id FROM services WHERE name='Electrician'")[0]["id"]
pid = q("SELECT p.id FROM providers p JOIN services s ON s.id=p.service_id "
        "WHERE s.name='Electrician' AND p.is_approved=1 AND p.address LIKE 'Thamel%' LIMIT 1")[0]["id"]
future = (date.today() + timedelta(days=9)).isoformat()
r = c_user.post(f"/book/{pid}/request", base_url="http://127.0.0.1:5000",
                data={"latitude": SATDOBATO[0], "longitude": SATDOBATO[1],
                      "address": "Satdobato, Lalitpur", "scheduled_date": future,
                      "scheduled_time": "09:00", "note": "AUDIT3 far", "estimated_hours": "1"})
bk = q("SELECT * FROM bookings WHERE note='AUDIT3 far' ORDER BY id DESC LIMIT 1")
check("far booking created", len(bk) == 1, str(r.status_code))
if bk:
    d = float(bk[0]["distance_km"])
    check("non-zero Dijkstra distance persisted", d > 5, f"{d} km")
    check("distance matches algorithm output", abs(d - 7.22) < 0.05, f"{d}")
    far_booking = bk[0]["id"]

print("\n########## 13. ADMIN OVERVIEW ##########")
r = c_admin.get("/admin/dashboard")
t = body(r)
check("admin dashboard renders", r.status_code == 200)
# The body carries the sidebar layout class alongside the admin one now.
check("admin console styling applied",
      'css/admin.css' in t and 'class="admin has-sidebar"' in t)
real_customers = q("SELECT COUNT(*) n FROM users WHERE role='user'")[0]["n"]
check("customer count matches database", f">{real_customers}<" in t, str(real_customers))
real_bookings = q("SELECT COUNT(*) n FROM bookings")[0]["n"]
check("booking count matches database", f">{real_bookings}<" in t, str(real_bookings))
for status in ["pending", "accepted", "rejected", "completed", "cancelled"]:
    check(f"status strip shows '{status}'", f"s-{status}" in t)

print("\n########## 14. ADMIN: PROVIDER APPROVAL AFFECTS SEARCH ##########")
unapproved = q("SELECT p.id, p.business_name FROM providers p WHERE p.is_approved=0 "
               "AND p.business_name='Limbu Electric Repair'")[0]
r = c_user.get(f"/search?service_id={elec}&latitude=27.7154&longitude=85.3123")
check("unapproved provider absent before approval", unapproved["business_name"] not in body(r))
c_admin.post(f"/admin/providers/{unapproved['id']}/toggle", follow_redirects=True)
check("approval persisted to DB",
      q("SELECT is_approved FROM providers WHERE id=%s", (unapproved["id"],))[0]["is_approved"] == 1)
r = c_user.get(f"/search?service_id={elec}&latitude=27.7154&longitude=85.3123")
check("approved provider now appears in search", unapproved["business_name"] in body(r))
c_admin.post(f"/admin/providers/{unapproved['id']}/toggle", follow_redirects=True)
r = c_user.get(f"/search?service_id={elec}&latitude=27.7154&longitude=85.3123")
check("deactivating removes it again", unapproved["business_name"] not in body(r))
r = c_admin.post("/admin/providers/999999/toggle", follow_redirects=True)
check("toggling unknown provider handled", "Provider not found" in body(r))

print("\n########## 15. ADMIN: USER DEACTIVATION ##########")
victim = q("SELECT id, email FROM users WHERE email='nirajan@example.com'")[0]
c_victim = new_client()
r = login(c_victim, victim["email"])
check("victim can log in before deactivation", r.status_code == 302)
c_admin.post(f"/admin/users/{victim['id']}/toggle", follow_redirects=True)
check("deactivation persisted", q("SELECT is_active FROM users WHERE id=%s", (victim["id"],))[0]["is_active"] == 0)
r = c_victim.get("/search")
check("existing session loses access immediately", r.status_code == 302 and "/login" in r.headers["Location"])
c_fresh = new_client()
r = login(c_fresh, victim["email"])
check("deactivated account cannot log in (403)", r.status_code == 403 and "deactivated" in body(r))
c_admin.post(f"/admin/users/{victim['id']}/toggle", follow_redirects=True)
r = login(new_client(), victim["email"])
check("reactivation restores login", r.status_code == 302)

admin_row = q("SELECT id FROM users WHERE role='admin' LIMIT 1")[0]
r = c_admin.post(f"/admin/users/{admin_row['id']}/toggle", follow_redirects=True)
check("admin account cannot be deactivated", "cannot be deactivated" in body(r))
check("admin still active", q("SELECT is_active FROM users WHERE id=%s", (admin_row["id"],))[0]["is_active"] == 1)
r = c_admin.post("/admin/users/999999/toggle", follow_redirects=True)
check("toggling unknown user handled", "User not found" in body(r))

print("\n########## 16. ADMIN: SERVICES ##########")
r = c_admin.post("/admin/services", data={"name": "Audit New Service", "icon": "🧪",
                                          "description": "Created by the audit"}, follow_redirects=True)
new_svc = q("SELECT * FROM services WHERE name='Audit New Service'")
check("service created in DB", len(new_svc) == 1)
check("new service shown on admin page", "Audit New Service" in body(r))
r = c_admin.post("/admin/services", data={"name": "Audit New Service", "icon": "x"}, follow_redirects=True)
check("duplicate service rejected", "already exists" in body(r))
check("still only one row", len(q("SELECT id FROM services WHERE name='Audit New Service'")) == 1)
r = c_admin.post("/admin/services", data={"name": "ab"}, follow_redirects=True)
check("too-short service name rejected", "at least" in body(r) or "required" in body(r))

svc_id = new_svc[0]["id"]
r = c_user.get("/search")
check("new service visible to customers", "Audit New Service" in body(r))
c_admin.post(f"/admin/services/{svc_id}/toggle", follow_redirects=True)
check("service hidden in DB", q("SELECT is_active FROM services WHERE id=%s", (svc_id,))[0]["is_active"] == 0)
r = c_user.get("/search")
check("hidden service removed from customer picker", "Audit New Service" not in body(r))
r = c_user.get(f"/search?service_id={svc_id}&latitude=27.7154&longitude=85.3123")
check("hidden service cannot be searched (404)", r.status_code == 404)

print("\n########## 17. ADMIN: BOOKINGS + FILTERS ##########")
r = c_admin.get("/admin/bookings")
check("admin bookings page renders", r.status_code == 200)
total = q("SELECT COUNT(*) n FROM bookings")[0]["n"]
# Rows became <tr class="row-link"> so each one can link to its detail page.
rows = body(r).count('class="row-link"')
check("all bookings listed", rows == min(total, 200), f"{rows} rows vs {total}")
for status in ["pending", "accepted", "completed", "cancelled", "rejected"]:
    r = c_admin.get(f"/admin/bookings?status={status}")
    n_db = q("SELECT COUNT(*) n FROM bookings WHERE status=%s", (status,))[0]["n"]
    n_html = body(r).count(f'badge-{status}">{status}')
    check(f"filter '{status}' matches DB ({n_db})", n_html == n_db, f"html={n_html} db={n_db}")
r = c_admin.get("/admin/bookings?status=INVALID")
check("invalid filter falls back to all", r.status_code == 200)

print("\n########## 18. PROFILE EDITING ##########")
r = c_user.post("/profile", data={"name": "Aarati R Regmi", "phone": "9800000011"}, follow_redirects=True)
check("customer profile saved",
      q("SELECT name, phone FROM users WHERE email='aarati@example.com'")[0]["phone"] == "9800000011")
r = c_user.post("/profile", data={"name": "Aarati", "phone": "12345"}, follow_redirects=True)
check("bad phone rejected", "Phone must be 10 digits" in body(r))
check("phone unchanged after rejection",
      q("SELECT phone FROM users WHERE email='aarati@example.com'")[0]["phone"] == "9800000011")

c_prov = new_client(); login(c_prov, "ramesh.s@example.com")
r = c_prov.get("/provider/profile")
check("provider profile page renders", r.status_code == 200 and "Shrestha Electric Works" in body(r))
r = c_prov.post("/provider/profile", data={
    "service_id": str(elec), "business_name": "Shrestha Electric Works",
    "hourly_rate": "875", "experience_years": "10", "bio": "Updated by audit",
    "address": "Thamel, Kathmandu", "latitude": "27.7154", "longitude": "85.3123",
    "is_available": "1"}, follow_redirects=True)
row = q("SELECT hourly_rate, experience_years, is_available FROM providers WHERE id=%s", (pid,))[0]
check("provider rate updated", float(row["hourly_rate"]) == 875.0, str(row["hourly_rate"]))
check("provider experience updated", row["experience_years"] == 10)
check("availability stays on when ticked", row["is_available"] == 1)

# untick availability -> disappears from search
r = c_prov.post("/provider/profile", data={
    "service_id": str(elec), "business_name": "Shrestha Electric Works",
    "hourly_rate": "875", "experience_years": "10", "bio": "x",
    "address": "Thamel, Kathmandu", "latitude": "27.7154", "longitude": "85.3123"},
    follow_redirects=True)
check("unticked checkbox sets unavailable",
      q("SELECT is_available FROM providers WHERE id=%s", (pid,))[0]["is_available"] == 0)
r = c_user.get(f"/search?service_id={elec}&latitude=27.7154&longitude=85.3123")
check("unavailable provider hidden from search", "Shrestha Electric Works" not in body(r))
r = c_user.get(f"/book/{pid}?latitude=27.7154&longitude=85.3123")
check("cannot open booking page for unavailable provider",
      r.status_code == 302 and "/search" in r.headers["Location"])
# restore
c_prov.post("/provider/profile", data={
    "service_id": str(elec), "business_name": "Shrestha Electric Works",
    "hourly_rate": "800", "experience_years": "9", "bio": "restored",
    "address": "Thamel, Kathmandu", "latitude": "27.7154", "longitude": "85.3123",
    "is_available": "1"}, follow_redirects=True)
check("provider restored", q("SELECT is_available FROM providers WHERE id=%s", (pid,))[0]["is_available"] == 1)

r = c_prov.post("/provider/profile", data={
    "service_id": str(elec), "business_name": "X", "hourly_rate": "800",
    "experience_years": "9", "address": "Thamel", "latitude": "40", "longitude": "-70",
    "is_available": "1"}, follow_redirects=True)
check("provider cannot move outside the valley", "outside the Kathmandu valley" in body(r))

print("\n########## 19. LIVE GALLI REVERSE-GEOCODE PROXY ##########")
r = c_user.get("/api/reverse-geocode?lat=27.7047&lng=85.3140")
check("reverse geocode returns 200", r.status_code == 200, str(r.status_code))
data = r.get_json()
check("returns ok=true with an address", data and data.get("ok") and len(data.get("address", "")) > 3,
      json.dumps(data)[:120])
print("        -> resolved:", (data or {}).get("address", "")[:90])
r = c_user.get("/api/reverse-geocode?lat=99&lng=999")
check("invalid coords -> 400 JSON", r.status_code == 400 and r.get_json().get("ok") is False)
r = c_user.get("/api/reverse-geocode?lat=abc&lng=def")
check("non-numeric coords -> 400 JSON", r.status_code == 400)
check("token never appears in the JSON response", "f2095659" not in body(r))

print("\n########## 20. ERROR HANDLING ##########")
r = c_user.get("/no-such-page")
check("404 page renders", r.status_code == 404 and "could not find that page" in body(r))
r = new_client().get("/")
check("landing page renders for anonymous visitor", r.status_code == 200 and "How it works" in body(r))
r = c_user.get("/")
check("logged-in customer redirected from landing to /search",
      r.status_code == 302 and "/search" in r.headers["Location"])
r = c_user.post("/logout", follow_redirects=False)
check("logout redirects to landing", r.status_code == 302)
r = c_user.get("/search")
check("session cleared after logout", r.status_code == 302 and "/login" in r.headers["Location"])

print(f"\n===== part 3: {len(PASS)} passed, {len(FAIL)} failed =====")
if FAIL:
    print("FAILURES:"); [print("   -", f) for f in FAIL]
