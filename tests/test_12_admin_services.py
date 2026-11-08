"""Admin services: update, delete, hide/show, and the per-service provider list."""
import os, sys, re
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
def cl(e):
    c = app.test_client()
    c.post("/login", data={"email": e, "password": support.SEED_PASSWORD}, base_url=BASE)
    return c
def body(r): return " ".join(r.get_data(as_text=True).split())

ex("DELETE FROM services WHERE name IN ('Audit Spare', 'Audit Renamed', 'Audit Clash')")

adm = cl("admin@serviceexpert.local")
cus = cl("aarati@example.com")
prv = cl("ramesh.s@example.com")

BUSY = q("SELECT s.id, s.name FROM services s JOIN providers p ON p.service_id = s.id "
         "GROUP BY s.id ORDER BY COUNT(p.id) DESC LIMIT 1")[0]
EMPTY_SQL = ("SELECT s.id, s.name FROM services s "
             "WHERE NOT EXISTS (SELECT 1 FROM providers p WHERE p.service_id = s.id) "
             "AND NOT EXISTS (SELECT 1 FROM bookings b WHERE b.service_id = s.id) LIMIT 1")

print("\n########## 113. THE ACTION COLUMN ##########")
t = body(adm.get("/admin/services", base_url=BASE))
services = q("SELECT id, name, is_active FROM services ORDER BY name")
check("services page loads", "Service categories" in t)
# The Account menu in the top bar is a <summary> too, so count only row menus.
rows = t.count('<details class="menu row-menu">')
check("one Actions menu per service", rows == len(services), f"{rows} vs {len(services)}")
check("Update offered", t.count(">Update<") == len(services))
check("Delete offered", t.count(">Delete<") == len(services))
check("Hide or Show offered on every row",
      t.count(">Hide<") + t.count(">Show<") == len(services),
      f"{t.count('>Hide<')} hide + {t.count('>Show<')} show")
for s in services:
    want = "Hide" if s["is_active"] else "Show"
    check(f"'{s['name']}' offers {want}",
          f'/admin/services/{s["id"]}/toggle" > <button type="submit">{want}<' in t
          or f'action="/admin/services/{s["id"]}/toggle"' in t)
check("Update is a link to the edit page",
      f'href="/admin/services/{services[0]["id"]}/edit"' in t)
check("Delete is a POST form, never a link",
      f'action="/admin/services/{services[0]["id"]}/delete"' in t
      and f'href="/admin/services/{services[0]["id"]}/delete"' not in t)
check("Delete asks for confirmation first", "onsubmit=\"return confirm(" in t)
check("the menu works without JavaScript (a details element)", "<details class=\"menu" in t)

print("\n########## 114. UPDATE ##########")
r = adm.get(f"/admin/services/{BUSY['id']}/edit", base_url=BASE)
t = body(r)
check("edit page loads", r.status_code == 200)
check("it is pre-filled with the current values",
      f'value="{BUSY["name"]}"' in t and 'name="icon"' in t and 'name="description"' in t)
check("it can be cancelled without saving", 'href="/admin/services"' in t)

ex("INSERT INTO services (name, icon, description) VALUES ('Audit Spare', '#', 'before')")
spare = q("SELECT id FROM services WHERE name='Audit Spare'")[0]["id"]
r = adm.post(f"/admin/services/{spare}/edit",
             data={"name": "Audit Renamed", "icon": "@", "description": "after"},
             base_url=BASE, follow_redirects=True)
row = q("SELECT name, icon, description FROM services WHERE id=%s", (spare,))[0]
check("name saved to the database", row["name"] == "Audit Renamed", row["name"])
check("icon saved", row["icon"] == "@", row["icon"])
check("description saved", row["description"] == "after", row["description"])
check("success message shown", "updated" in body(r).lower())
check("the change appears on the services page", "Audit Renamed" in body(r))

r = adm.post(f"/admin/services/{spare}/edit",
             data={"name": BUSY["name"], "icon": "@", "description": "after"},
             base_url=BASE, follow_redirects=True)
check("a duplicate name is refused", "already uses that name" in body(r))
check("nothing was overwritten",
      q("SELECT name FROM services WHERE id=%s", (spare,))[0]["name"] == "Audit Renamed")
r = adm.post(f"/admin/services/{spare}/edit",
             data={"name": "Audit Renamed", "icon": "@", "description": "same name kept"},
             base_url=BASE, follow_redirects=True)
check("saving without renaming is allowed",
      q("SELECT description FROM services WHERE id=%s", (spare,))[0]["description"]
      == "same name kept")
r = adm.post(f"/admin/services/{spare}/edit", data={"name": "ab"},
             base_url=BASE, follow_redirects=True)
check("a too-short name is refused", "at least" in body(r))
r = adm.get("/admin/services/999999/edit", base_url=BASE, follow_redirects=True)
check("editing an unknown service is handled", "Service not found" in body(r))

print("\n########## 115. DELETE ##########")
before = q("SELECT COUNT(*) n FROM services")[0]["n"]
r = adm.post(f"/admin/services/{BUSY['id']}/delete", base_url=BASE, follow_redirects=True)
t = body(r)
check("a service with providers is NOT deleted",
      q("SELECT COUNT(*) n FROM services WHERE id=%s", (BUSY["id"],))[0]["n"] == 1)
check("and the reason names the providers", "cannot be deleted because" in t and "provider" in t)
check("it suggests hiding instead", "Hide it instead" in t)
check("no other service was touched",
      q("SELECT COUNT(*) n FROM services")[0]["n"] == before)

# A service used only by past bookings must also survive.
booked = q("SELECT s.id, s.name FROM services s JOIN bookings b ON b.service_id = s.id "
           "LIMIT 1")
if booked:
    r = adm.post(f"/admin/services/{booked[0]['id']}/delete", base_url=BASE,
                 follow_redirects=True)
    check("a service used by bookings is NOT deleted",
          q("SELECT COUNT(*) n FROM services WHERE id=%s", (booked[0]["id"],))[0]["n"] == 1)
    check("and the booking records are still there",
          q("SELECT COUNT(*) n FROM bookings WHERE service_id=%s",
            (booked[0]["id"],))[0]["n"] > 0)

free = q(EMPTY_SQL)
check("the spare service is free to delete", len(free) > 0)
if free:
    target = free[0]
    r = adm.post(f"/admin/services/{target['id']}/delete", base_url=BASE,
                 follow_redirects=True)
    check("an unused service IS deleted",
          q("SELECT COUNT(*) n FROM services WHERE id=%s", (target["id"],))[0]["n"] == 0)
    check("with a success message", "deleted" in body(r).lower())

r = adm.post("/admin/services/999999/delete", base_url=BASE, follow_redirects=True)
check("deleting an unknown service is handled", "Service not found" in body(r))
r = adm.get(f"/admin/services/{BUSY['id']}/delete", base_url=BASE)
check("delete cannot be done with a GET", r.status_code == 405, str(r.status_code))

print("\n########## 116. HIDE AND SHOW STILL WORK ##########")
ex("INSERT INTO services (name, icon, description) VALUES ('Audit Spare', '#', 'toggle me')")
spare2 = q("SELECT id FROM services WHERE name='Audit Spare'")[0]["id"]
check("a new service starts visible",
      q("SELECT is_active FROM services WHERE id=%s", (spare2,))[0]["is_active"] == 1)
check("and a customer can see it", "Audit Spare" in body(cus.get("/search", base_url=BASE)))
t = body(adm.get("/admin/services", base_url=BASE))
check("its menu says Hide", f'action="/admin/services/{spare2}/toggle"' in t
      and ">Hide<" in t)

adm.post(f"/admin/services/{spare2}/toggle", base_url=BASE, follow_redirects=True)
check("hiding is stored",
      q("SELECT is_active FROM services WHERE id=%s", (spare2,))[0]["is_active"] == 0)
check("a hidden service disappears from the customer search",
      "Audit Spare" not in body(cus.get("/search", base_url=BASE)))
t = body(adm.get("/admin/services", base_url=BASE))
check("the button now says Show", ">Show<" in t)
check("and the row is marked Hidden", "Hidden" in t)

adm.post(f"/admin/services/{spare2}/toggle", base_url=BASE, follow_redirects=True)
check("showing it again is stored",
      q("SELECT is_active FROM services WHERE id=%s", (spare2,))[0]["is_active"] == 1)
check("and the customer sees it once more",
      "Audit Spare" in body(cus.get("/search", base_url=BASE)))

# Hiding must never remove providers.
kept = q("SELECT COUNT(*) n FROM providers WHERE service_id=%s", (BUSY["id"],))[0]["n"]
adm.post(f"/admin/services/{BUSY['id']}/toggle", base_url=BASE, follow_redirects=True)
check("hiding a busy service keeps every provider row",
      q("SELECT COUNT(*) n FROM providers WHERE service_id=%s", (BUSY["id"],))[0]["n"] == kept)
adm.post(f"/admin/services/{BUSY['id']}/toggle", base_url=BASE, follow_redirects=True)
check("and it is visible again",
      q("SELECT is_active FROM services WHERE id=%s", (BUSY["id"],))[0]["is_active"] == 1)

print("\n########## 117. CLICKING A SERVICE NAME ##########")
t = body(adm.get("/admin/services", base_url=BASE))
for s in q("SELECT id, name FROM services ORDER BY name"):
    check(f"'{s['name']}' is a link to its own provider list",
          f'href="/admin/services/{s["id"]}/providers"' in t)

for s in q("SELECT id, name FROM services ORDER BY name"):
    r = adm.get(f"/admin/services/{s['id']}/providers", base_url=BASE)
    t = body(r)
    check(f"{s['name']} page loads", r.status_code == 200, str(r.status_code))
    check(f"{s['name']} page is titled after the service",
          f"{s['name']} providers" in t)

    mine = q("SELECT p.business_name FROM providers p WHERE p.service_id=%s", (s["id"],))
    others = q("SELECT p.business_name FROM providers p WHERE p.service_id<>%s", (s["id"],))
    missing = [m["business_name"] for m in mine if m["business_name"] not in t]
    check(f"{s['name']}: all {len(mine)} of its providers are listed",
          not missing, str(missing[:3]))
    leaked = [o["business_name"] for o in others if o["business_name"] in t]
    check(f"{s['name']}: no provider from another service appears",
          not leaked, str(leaked[:3]))
    if not mine:
        check(f"{s['name']}: says so plainly when empty",
              f"No providers found for {s['name']}." in t, t[:160])
    else:
        check(f"{s['name']}: the Service column is dropped (all rows are the same)",
              "<th>Service</th>" not in t)

check("the count in the table matches the filtered page",
      all(
          str(row["provider_count"]) and
          len(q("SELECT id FROM providers WHERE service_id=%s", (row["id"],)))
          == row["provider_count"]
          for row in q("SELECT s.id, COUNT(p.id) AS provider_count FROM services s "
                       "LEFT JOIN providers p ON p.service_id=s.id GROUP BY s.id")
      ))
r = adm.get("/admin/services/999999/providers", base_url=BASE, follow_redirects=True)
check("an unknown service id is handled", "Service not found" in body(r))

print("\n########## 118. ONLY THE ADMIN CAN DO ANY OF THIS ##########")
paths = [f"/admin/services/{BUSY['id']}/edit", f"/admin/services/{BUSY['id']}/providers"]
posts = [f"/admin/services/{BUSY['id']}/delete", f"/admin/services/{BUSY['id']}/toggle"]
for role, client in [("customer", cus), ("provider", prv)]:
    for path in paths:
        check(f"{role} refused GET {path}",
              client.get(path, base_url=BASE).status_code == 302)
    for path in posts:
        check(f"{role} refused POST {path}",
              client.post(path, base_url=BASE).status_code == 302)
anon = app.test_client()
for path in paths:
    r = anon.get(path, base_url=BASE)
    check(f"anonymous refused {path}",
          r.status_code == 302 and "/login" in r.headers.get("Location", ""))
for path in posts:
    check(f"anonymous refused POST {path}",
          anon.post(path, base_url=BASE).status_code == 302)
check("a customer could not delete anything",
      q("SELECT COUNT(*) n FROM services WHERE id=%s", (BUSY["id"],))[0]["n"] == 1)

print("\n########## 119. THE REST OF THE SERVICE FLOW IS INTACT ##########")
t = body(adm.get("/admin/providers", base_url=BASE))
check("the full provider list still renders", "Service providers" in t)
check("it still shows the Service column", "<th>Service</th>" in t)
check("it still has its approve/deactivate buttons",
      "Deactivate" in t or "Approve" in t)
all_providers = q("SELECT COUNT(*) n FROM providers")[0]["n"]
check("it still lists every provider",
      t.count("/admin/providers/") >= all_providers, str(t.count("/admin/providers/")))
r = adm.post("/admin/services", data={"name": "Audit Clash", "icon": "!",
                                      "description": "added the old way"},
             base_url=BASE, follow_redirects=True)
check("adding a service still works",
      q("SELECT COUNT(*) n FROM services WHERE name='Audit Clash'")[0]["n"] == 1)
check("a duplicate add is still refused",
      "already exists" in body(adm.post("/admin/services", data={"name": "Audit Clash"},
                                        base_url=BASE, follow_redirects=True)))
t = body(cus.get("/search", base_url=BASE))
check("the customer service picker still works", "Audit Clash" in t)

ex("DELETE FROM services WHERE name IN ('Audit Spare', 'Audit Renamed', 'Audit Clash')")
print(f"\n===== admin services: {len(PASS)} passed, {len(FAIL)} failed =====")
if FAIL:
    print("FAILURES:")
    for f in FAIL:
        print("   -", f)
