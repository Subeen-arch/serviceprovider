"""The View map link on the admin provider list, and the single-provider map."""
import os, sys, re
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tests import support
support.use_test_database()   # must happen before app is imported

from app import app

BASE = support.BASE
q, ex, body = support.q, support.ex, support.body
results = support.Results("provider location")
check, section = results.check, results.section

adm = support.client(support.ADMIN_EMAIL)
cus = support.client(support.CUSTOMER_EMAIL)
prv = support.client(support.PROVIDER_EMAIL)

providers = q("SELECT p.id, p.business_name, p.address, p.latitude, p.longitude, "
              "p.is_approved, u.name AS owner, u.email, u.phone, s.name AS service "
              "FROM providers p JOIN users u ON u.id = p.user_id "
              "JOIN services s ON s.id = p.service_id ORDER BY p.id")
ONE = providers[0]

section("120. EVERY ROW OFFERS A MAP")
t = body(adm.get("/admin/providers", base_url=BASE))
check("provider list loads", "Service providers" in t)
check("a link for every provider",
      t.count("View map") == len(providers),
      f"{t.count('View map')} links for {len(providers)} providers")
for provider in providers:
    check(f"#{provider['id']} {provider['business_name'][:26]} has its own link",
          f'href="/admin/providers/{provider["id"]}/location"' in t)
check("the pin is shown beside the address", t.count("&#128205;") >= len(providers)
      or t.count("\U0001f4cd") >= len(providers))
check("the address is still printed in the row", ONE["address"] in t)
check("each link names its provider for a screen reader",
      f'View map<span class="sr-only"> for {ONE["business_name"]}' in t)

# The same table is used by the per-service page, so the link comes with it.
service_id = q("SELECT s.id FROM services s JOIN providers p ON p.service_id = s.id "
               "GROUP BY s.id LIMIT 1")[0]["id"]
t = body(adm.get(f"/admin/services/{service_id}/providers", base_url=BASE))
mine = q("SELECT id FROM providers WHERE service_id = %s", (service_id,))
check("the per-service page offers it too",
      t.count("View map") == len(mine), f"{t.count('View map')} vs {len(mine)}")

section("121. THE MAP PAGE SHOWS ONE PROVIDER ONLY")
for provider in providers[:6]:
    r = adm.get(f"/admin/providers/{provider['id']}/location", base_url=BASE)
    t = body(r)
    check(f"#{provider['id']} page loads", r.status_code == 200, str(r.status_code))
    check(f"#{provider['id']} is named on it", provider["business_name"] in t)
    check(f"#{provider['id']} shows its own address", provider["address"] in t)

    # The whole point: nobody else's shop may appear.
    others = [p for p in providers if p["id"] != provider["id"]
              and p["business_name"] != provider["business_name"]]
    leaked = [p["business_name"] for p in others if p["business_name"] in t]
    check(f"#{provider['id']} shows no other provider", not leaked, str(leaked[:3]))

    # Exactly one pair of coordinates reaches the page, and it is the right one.
    coordinates = re.findall(r"lat: ([-\d.]+),\s*lng: ([-\d.]+)", t)
    check(f"#{provider['id']} passes exactly one point to the map",
          len(coordinates) == 1, str(coordinates))
    if coordinates:
        lat, lng = float(coordinates[0][0]), float(coordinates[0][1])
        check(f"#{provider['id']} uses its own coordinates",
              abs(lat - float(provider["latitude"])) < 1e-6
              and abs(lng - float(provider["longitude"])) < 1e-6,
              f"{lat},{lng} vs {provider['latitude']},{provider['longitude']}")

section("122. WHAT THE PAGE CONTAINS")
t = body(adm.get(f"/admin/providers/{ONE['id']}/location", base_url=BASE))
check("owner name shown", ONE["owner"] in t)
check("owner email shown", ONE["email"] in t)
check("owner phone shown", ONE["phone"] in t)
check("service shown", ONE["service"] in t)
check("approval state shown", "Approved" in t or "Pending" in t)
check("booking count shown", "Bookings" in t)
check("a single-marker map is used, not the route map",
      "initPlaceMap" in t and "initRouteMap" not in t)
check("no route status line", "Finding the road route" not in t)
check("the Galli SDK is loaded", "gallimaps.vector.min.latest.js" in t)
check("the map token is not a secret key",
      "KHALTI" not in t and "SECRET" not in t.upper())
check("it links back to the provider list", 'href="/admin/providers"' in t)
check("approve or deactivate can be done from here",
      f'action="/admin/providers/{ONE["id"]}/toggle"' in t)

section("123. THE APPROVE ACTION STILL WORKS FROM THE MAP PAGE")
before = q("SELECT is_approved FROM providers WHERE id=%s", (ONE["id"],))[0]["is_approved"]
adm.post(f"/admin/providers/{ONE['id']}/toggle", base_url=BASE, follow_redirects=True)
after = q("SELECT is_approved FROM providers WHERE id=%s", (ONE["id"],))[0]["is_approved"]
check("toggling from that page changes the database", after != before)
adm.post(f"/admin/providers/{ONE['id']}/toggle", base_url=BASE, follow_redirects=True)
check("and it can be put back",
      q("SELECT is_approved FROM providers WHERE id=%s",
        (ONE["id"],))[0]["is_approved"] == before)

section("124. BAD INPUT AND ACCESS CONTROL")
r = adm.get("/admin/providers/999999/location", base_url=BASE, follow_redirects=True)
check("an unknown provider is handled", "Provider not found" in body(r))
r = adm.get("/admin/providers/abc/location", base_url=BASE)
check("a non-numeric id is a 404, not a crash", r.status_code == 404, str(r.status_code))

path = f"/admin/providers/{ONE['id']}/location"
for role, client in [("customer", cus), ("provider", prv)]:
    r = client.get(path, base_url=BASE)
    check(f"{role} cannot open it", r.status_code == 302, str(r.status_code))
r = app.test_client().get(path, base_url=BASE)
check("anonymous is sent to the login page",
      r.status_code == 302 and "/login" in r.headers.get("Location", ""))
check("a provider cannot read another provider's page this way",
      prv.get(f"/admin/providers/{providers[-1]['id']}/location",
              base_url=BASE).status_code == 302)

section("125. THE PROVIDER LIST IS OTHERWISE UNCHANGED")
t = body(adm.get("/admin/providers", base_url=BASE))
check("approve / deactivate buttons still there", "Approve" in t or "Deactivate" in t)
check("the status filters still work",
      'href="/admin/providers?status=pending"' in t)
pending = q("SELECT COUNT(*) n FROM providers WHERE is_approved=0")[0]["n"]
t = body(adm.get("/admin/providers?status=pending", base_url=BASE))
check(f"the pending filter still lists {pending}",
      t.count("View map") == pending, f"{t.count('View map')} vs {pending}")
check("every column is still present",
      all(h in t for h in ["Business", "Owner", "Service", "Rate", "Exp.",
                           "Rating", "Status", "Action"]))

raise SystemExit(results.report() and 1 or 0)
