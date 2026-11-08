"""End-to-end integration audit against a real MySQL 8 server."""
import os, sys, re
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tests import support
support.use_test_database()   # must happen before app is imported

import mysql.connector
from app import app

app.config["TESTING"] = False  # keep real error handling
PASS, FAIL = [], []

def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(("  PASS  " if cond else "  FAIL  ") + name + (f"   [{detail}]" if detail and not cond else ""))

def q(sql, params=()):
    c = support.connect()
    cur = c.cursor(dictionary=True); cur.execute(sql, params)
    rows = cur.fetchall(); cur.close(); c.close(); return rows

def client():
    return app.test_client()

def login(c, email, pw=support.SEED_PASSWORD):
    return c.post("/login", data={"email": email, "password": pw}, follow_redirects=False)

def body(r):
    return r.get_data(as_text=True)

def purge():
    """Remove anything an earlier audit run created, so the run is repeatable."""
    c = support.connect()
    cur = c.cursor()
    cur.execute("DELETE FROM users WHERE email IN ('newcust@example.com','provtest@example.com')")
    c.commit(); cur.close(); c.close()

purge()

print("\n########## 1. ACCESS CONTROL (anonymous) ##########")
c = client()
for path in ["/search", "/bookings", "/profile", "/provider/dashboard", "/admin/dashboard",
             "/admin/users", "/admin/providers", "/admin/services", "/admin/bookings",
             "/api/reverse-geocode?lat=27.7&lng=85.3"]:
    r = c.get(path)
    check(f"anon GET {path} -> login redirect", r.status_code == 302 and "/login" in r.headers.get("Location",""),
          f"{r.status_code} {r.headers.get('Location')}")
for path in ["/bookings/1/cancel", "/bookings/1/review", "/provider/bookings/1/accept",
             "/admin/users/1/toggle", "/admin/providers/1/toggle", "/admin/services/1/toggle", "/logout"]:
    r = c.post(path)
    check(f"anon POST {path} -> login redirect", r.status_code == 302 and "/login" in r.headers.get("Location",""),
          f"{r.status_code}")

print("\n########## 2. REGISTRATION VALIDATION ##########")
c = client()
r = c.post("/register", data={"name":"Ab","email":"bad","phone":"123","password":"short",
                              "confirm_password":"nope","role":"user"})
t = body(r)
check("weak form rejected with 400", r.status_code == 400, str(r.status_code))
for msg in ["Name must be at least 3", "valid email address", "Phone must be 10 digits",
            "at least 8 characters", "do not match"]:
    check(f"error shown: '{msg}'", msg in t)
check("no user created", len(q("SELECT id FROM users WHERE email='bad'")) == 0)

r = c.post("/register", data={"name":"Aarati Regmi","email":"aarati@example.com","phone":"9800000009",
                              "password":"Testpass1","confirm_password":"Testpass1","role":"user"})
check("duplicate email rejected", r.status_code == 400 and "already exists" in body(r))

r = c.post("/register", data={"name":"Test Customer","email":"newcust@example.com","phone":"9800001234",
                              "password":"Testpass1","confirm_password":"Testpass1","role":"user"},
           follow_redirects=False)
check("valid customer registered -> redirect to login", r.status_code == 302 and "/login" in r.headers["Location"])
row = q("SELECT password_hash, role FROM users WHERE email='newcust@example.com'")
check("customer row created with role=user", row and row[0]["role"] == "user")
check("password is hashed, not plaintext",
      row and "Testpass1" not in row[0]["password_hash"] and len(row[0]["password_hash"]) > 40)

# provider registration missing map coords
r = c.post("/register", data={"name":"Prov Test","email":"provtest@example.com","phone":"9800005678",
                              "password":"Testpass1","confirm_password":"Testpass1","role":"provider",
                              "service_id":"1","business_name":"Test Biz","hourly_rate":"500",
                              "experience_years":"3","address":"Somewhere","latitude":"","longitude":""})
check("provider without map location rejected", r.status_code == 400 and "select a location" in body(r))
# provider with out-of-valley coords
r = c.post("/register", data={"name":"Prov Test","email":"provtest@example.com","phone":"9800005678",
                              "password":"Testpass1","confirm_password":"Testpass1","role":"provider",
                              "service_id":"1","business_name":"Test Biz","hourly_rate":"500",
                              "experience_years":"3","address":"Somewhere","latitude":"40.0","longitude":"-70.0"})
check("provider outside valley rejected", r.status_code == 400 and "outside the Kathmandu valley" in body(r))
# valid provider
sid = q("SELECT id FROM services WHERE name='Plumber'")[0]["id"]
r = c.post("/register", data={"name":"Prov Test","email":"provtest@example.com","phone":"9800005678",
                              "password":"Testpass1","confirm_password":"Testpass1","role":"provider",
                              "service_id":str(sid),"business_name":"Test Plumbing","hourly_rate":"500",
                              "experience_years":"3","address":"Teku","latitude":"27.6960","longitude":"85.3062"},
           follow_redirects=False)
check("valid provider registered", r.status_code == 302)
pr = q("SELECT is_approved, is_available FROM providers p JOIN users u ON u.id=p.user_id WHERE u.email='provtest@example.com'")
check("new provider starts unapproved", pr and pr[0]["is_approved"] == 0)

print("\n########## 3. LOGIN ##########")
c = client()
r = login(c, "aarati@example.com", "WrongPass1")
check("wrong password -> 401", r.status_code == 401 and "Incorrect email or password" in body(r))
r = login(c, "nobody@example.com", support.SEED_PASSWORD)
check("unknown email -> same generic 401", r.status_code == 401 and "Incorrect email or password" in body(r))

c_user = client(); r = login(c_user, "aarati@example.com")
check("customer login -> /search", r.status_code == 302 and r.headers["Location"].endswith("/search"))
c_prov = client(); r = login(c_prov, "ramesh.s@example.com")
check("provider login -> /provider/dashboard", r.status_code == 302 and "/provider/dashboard" in r.headers["Location"])
c_admin = client(); r = login(c_admin, "admin@serviceexpert.local")
check("admin login -> /admin/dashboard", r.status_code == 302 and "/admin/dashboard" in r.headers["Location"])

print("\n########## 4. ROLE ENFORCEMENT (server side) ##########")
for name, cl, blocked in [("customer", c_user, ["/provider/dashboard","/provider/profile","/admin/dashboard","/admin/users","/admin/providers","/admin/services","/admin/bookings"]),
                          ("provider", c_prov, ["/search","/bookings","/admin/dashboard","/admin/users"]),
                          ("admin",    c_admin, ["/search","/bookings","/provider/dashboard"])]:
    for path in blocked:
        r = cl.get(path)
        loc = r.headers.get("Location", "")
        check(f"{name} blocked from {path}",
              r.status_code == 302 and not loc.endswith(path),
              f"{r.status_code} -> {loc}")
    # POST endpoints too
for path in ["/admin/users/1/toggle", "/admin/providers/1/toggle"]:
    r = c_user.post(path)
    check(f"customer blocked from POST {path}", r.status_code == 302 and "/search" in r.headers.get("Location",""))
r = c_prov.post("/bookings/1/cancel")
check("provider blocked from customer cancel", r.status_code == 302 and "/provider" in r.headers.get("Location",""))

print(f"\n===== part 1 done: {len(PASS)} passed, {len(FAIL)} failed =====")
if FAIL:
    print("FAILURES:"); [print("   -", f) for f in FAIL]
