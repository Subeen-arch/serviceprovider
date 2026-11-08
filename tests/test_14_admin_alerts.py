"""Admin notifications for the events that matter, and the cancellation reason."""
import os, sys
from datetime import date, timedelta
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tests import support
support.use_test_database()   # must happen before app is imported

from app import app

BASE = support.BASE
q, ex, body = support.q, support.ex, support.body
results = support.Results("admin alerts")
check, section = results.check, results.section

ADMINS = [row["id"] for row in q("SELECT id FROM users WHERE role='admin' AND is_active=1")]


def clear_alerts():
    ex("DELETE FROM notifications WHERE user_id IN (%s)" %
       ",".join(str(i) for i in ADMINS))


def alerts(title=None):
    sql = ("SELECT title, message, booking_id, user_id FROM notifications "
           "WHERE user_id IN (%s) " % ",".join(str(i) for i in ADMINS))
    if title:
        sql += "AND title = %s "
        return q(sql + "ORDER BY id", (title,))
    return q(sql + "ORDER BY id")


adm = support.client(support.ADMIN_EMAIL)
cus = support.client(support.CUSTOMER_EMAIL)
prv = support.client(support.PROVIDER_EMAIL)

profile = q("SELECT p.id, p.business_name, p.address, p.service_id, p.is_available, "
            "p.bio, p.hourly_rate, p.experience_years, p.latitude, p.longitude "
            "FROM providers p JOIN users u ON u.id=p.user_id "
            "WHERE u.email=%s", (support.PROVIDER_EMAIL,))[0]


def save_profile(**changes):
    form = {
        "service_id": profile["service_id"],
        "business_name": profile["business_name"],
        "bio": profile["bio"] or "A bio",
        "hourly_rate": str(profile["hourly_rate"]),
        "experience_years": str(profile["experience_years"]),
        "address": profile["address"],
        "latitude": str(profile["latitude"]),
        "longitude": str(profile["longitude"]),
    }
    if profile["is_available"]:
        form["is_available"] = "1"
    form.update(changes)
    return prv.post("/provider/profile", data=form, base_url=BASE, follow_redirects=True)


section("126. THE COLUMNS THE FEATURE NEEDS")
DB = os.environ["DB_NAME"]
for table, column in [("notifications", "title"), ("bookings", "cancel_reason")]:
    row = q("SELECT DATA_TYPE, IS_NULLABLE, COLUMN_DEFAULT FROM information_schema.COLUMNS "
            "WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s AND COLUMN_NAME=%s",
            (DB, table, column))
    check(f"{table}.{column} exists", len(row) == 1)
    if row:
        check(f"{table}.{column} defaults to empty, so old rows still read",
              row[0]["COLUMN_DEFAULT"] == "" and row[0]["IS_NULLABLE"] == "NO",
              str(row[0]))

section("127. PROVIDER MOVES SHOP")
clear_alerts()
was = profile["address"]
r = save_profile(address="Satdobato, Lalitpur")
got = alerts("Provider Location Updated")
check("one alert per administrator", len(got) == len(ADMINS), str(len(got)))
if got:
    check("it names the provider", profile["business_name"] in got[0]["message"])
    check("it gives the old address", was in got[0]["message"], got[0]["message"])
    check("it gives the new address", "Satdobato, Lalitpur" in got[0]["message"])
    check("worded as the spec asks",
          "changed their business location from" in got[0]["message"],
          got[0]["message"])

clear_alerts()
save_profile(address="Satdobato, Lalitpur")      # same address again
check("saving the same address raises nothing", not alerts("Provider Location Updated"))
clear_alerts()
save_profile(address="Satdobato, Lalitpur", bio="A completely new bio here")
check("changing only the bio raises nothing", not alerts(), str(alerts()))
clear_alerts()
save_profile(address="Satdobato, Lalitpur", hourly_rate="911")
check("changing only the price raises nothing", not alerts())
save_profile(address=was, hourly_rate=str(profile["hourly_rate"]))   # put it back

section("128. PROVIDER CHANGES WORKING HOURS")
clear_alerts()
ex("DELETE FROM provider_availability WHERE provider_id = %s", (profile["id"],))
prv.post("/provider/availability", data={
    "work_0": "1", "start_0": "09:00", "end_0": "17:00",
}, base_url=BASE, follow_redirects=True)
clear_alerts()
prv.post("/provider/availability", data={
    "work_0": "1", "start_0": "10:00", "end_0": "18:00",
}, base_url=BASE, follow_redirects=True)
got = alerts("Service Availability Updated")
check("an alert is raised", len(got) == len(ADMINS), str(len(got)))
if got:
    message = got[0]["message"]
    check("it names the provider", profile["business_name"] in message)
    check("it gives the old hours", "09:00 AM - 05:00 PM" in message, message)
    check("it gives the new hours", "10:00 AM - 06:00 PM" in message, message)
    check("worded as the spec asks",
          "changed their available service time from" in message, message)

clear_alerts()
prv.post("/provider/availability", data={
    "work_0": "1", "start_0": "10:00", "end_0": "18:00",
}, base_url=BASE, follow_redirects=True)
check("saving the same hours raises nothing", not alerts("Service Availability Updated"))

section("129. BOOKING CANCELLED, WITH A REASON")
clear_alerts()
booking = q("SELECT b.id, b.user_id, s.name AS service, p.business_name, cu.name AS customer "
            "FROM bookings b JOIN services s ON s.id=b.service_id "
            "JOIN providers p ON p.id=b.provider_id JOIN users cu ON cu.id=b.user_id "
            "WHERE cu.email=%s AND b.status IN ('pending','accepted') LIMIT 1",
            (support.CUSTOMER_EMAIL,))
if not booking:
    # Put one back into a cancellable state so the check can run.
    row = q("SELECT b.id FROM bookings b JOIN users cu ON cu.id=b.user_id "
            "WHERE cu.email=%s LIMIT 1", (support.CUSTOMER_EMAIL,))[0]
    ex("UPDATE bookings SET status='pending' WHERE id=%s", (row["id"],))
    booking = q("SELECT b.id, b.user_id, s.name AS service, p.business_name, "
                "cu.name AS customer FROM bookings b JOIN services s ON s.id=b.service_id "
                "JOIN providers p ON p.id=b.provider_id JOIN users cu ON cu.id=b.user_id "
                "WHERE b.id=%s", (row["id"],))
BK = booking[0]

REASON = "I found another provider"
r = cus.post(f"/bookings/{BK['id']}/cancel", data={"reason": REASON},
             base_url=BASE, follow_redirects=True)
check("the booking is cancelled",
      q("SELECT status FROM bookings WHERE id=%s", (BK["id"],))[0]["status"] == "cancelled")
check("the reason is stored, not just shown",
      q("SELECT cancel_reason FROM bookings WHERE id=%s",
        (BK["id"],))[0]["cancel_reason"] == REASON)

got = alerts("Booking Cancelled")
check("an alert is raised", len(got) == len(ADMINS), str(len(got)))
if got:
    message = got[0]["message"]
    check("it gives the booking number", f"#{BK['id']}" in message, message)
    check("it names the service", BK["service"] in message, message)
    check("it names the provider", BK["business_name"] in message, message)
    check("it names the customer", BK["customer"] in message, message)
    check("it carries the reason", REASON in message, message)
    check("it links back to the booking", got[0]["booking_id"] == BK["id"])

section("130. PAYMENT REFUNDED")
clear_alerts()
paid = q("SELECT b.id, pay.amount, cu.name AS customer FROM bookings b "
         "JOIN payments pay ON pay.booking_id=b.id JOIN users cu ON cu.id=b.user_id "
         "WHERE cu.email=%s LIMIT 1", (support.CUSTOMER_EMAIL,))
if paid:
    target = paid[0]
    ex("UPDATE bookings SET status='accepted', cancel_reason='' WHERE id=%s", (target["id"],))
    ex("UPDATE payments SET status='paid', refunded_at=NULL WHERE booking_id=%s",
       (target["id"],))
    cus.post(f"/bookings/{target['id']}/cancel", data={"reason": "Changed my mind"},
             base_url=BASE, follow_redirects=True)
    check("the payment is marked refunded",
          q("SELECT status FROM payments WHERE booking_id=%s",
            (target["id"],))[0]["status"] == "refunded")
    got = alerts("Payment Refunded")
    check("a refund alert is raised", len(got) == len(ADMINS), str(len(got)))
    if got:
        message = got[0]["message"]
        check("it gives the amount in rupees",
              f"Rs. {float(target['amount']):.0f}" in message, message)
        check("it names the customer", target["customer"] in message, message)
        check("it gives the booking number", f"#{target['id']}" in message, message)

section("131. NEW PROVIDER WAITING FOR APPROVAL")
clear_alerts()
ex("DELETE FROM users WHERE email='alerttest@example.com'")
service = q("SELECT id FROM services WHERE is_active=1 LIMIT 1")[0]["id"]
r = app.test_client().post("/register", data={
    "role": "provider", "name": "Alert Test Owner", "email": "alerttest@example.com",
    "phone": "9801000777", "password": "Testpass123", "confirm_password": "Testpass123",
    "service_id": service, "business_name": "Alert Test Repairs",
    "bio": "Testing the approval alert", "hourly_rate": "500", "experience_years": "2",
    "address": "Jorpati, Kathmandu", "latitude": "27.7172", "longitude": "85.3240",
}, base_url=BASE, follow_redirects=True)
check("the provider account was created",
      q("SELECT COUNT(*) n FROM users WHERE email='alerttest@example.com'")[0]["n"] == 1)
got = alerts("New Provider Waiting for Approval")
check("an alert is raised", len(got) == len(ADMINS), str(len(got)))
if got:
    check("it names the business", "Alert Test Repairs" in got[0]["message"], got[0]["message"])
    check("worded as the spec asks",
          "has registered and is waiting for approval" in got[0]["message"])

clear_alerts()
app.test_client().post("/register", data={
    "role": "user", "name": "Alert Test Customer", "email": "alertcust@example.com",
    "phone": "9801000778", "password": "Testpass123", "confirm_password": "Testpass123",
}, base_url=BASE, follow_redirects=True)
check("a plain customer signing up raises nothing", not alerts(), str(alerts()))
ex("DELETE FROM users WHERE email IN ('alerttest@example.com','alertcust@example.com')")

section("132. THE BELL IS NOT FILLED WITH NOISE")
clear_alerts()
pending = q("SELECT b.id FROM bookings b WHERE b.status='pending' LIMIT 1")
if pending:
    prov_of = q("SELECT u.email FROM bookings b JOIN providers p ON p.id=b.provider_id "
                "JOIN users u ON u.id=p.user_id WHERE b.id=%s", (pending[0]["id"],))[0]
    owner = support.client(prov_of["email"])
    owner.post(f"/provider/bookings/{pending[0]['id']}/accept", base_url=BASE,
               follow_redirects=True)
    check("accepting a booking raises no admin alert", not alerts(), str(alerts()))
adm.post("/admin/services", data={"name": "Alert Noise Check", "icon": "!",
                                  "description": "should be silent"},
         base_url=BASE, follow_redirects=True)
check("an admin adding a service raises no alert", not alerts())
ex("DELETE FROM services WHERE name='Alert Noise Check'")
cus.post("/profile", data={"name": "Aarati Shrestha", "phone": "9801000001"},
         base_url=BASE, follow_redirects=True)
check("a customer editing their profile raises no alert", not alerts())

section("133. THE ALERTS PAGE SHOWS THEM")
clear_alerts()
save_profile(address="Ekantakuna, Lalitpur")
# The badge is read first: opening the alerts page marks everything read, so
# checking it afterwards would always find the badge gone.
check("the bell counts it",
      'class="icon-badge"' in body(adm.get("/admin/dashboard", base_url=BASE)))
t = body(adm.get("/notifications", base_url=BASE))
check("the heading is shown", "Provider Location Updated" in t)
check("the message is shown", "changed their business location from" in t)
check("reading the page clears the badge",
      "icon-badge" not in body(adm.get("/admin/dashboard", base_url=BASE)))
save_profile(address=was)

section("134. THE CANCELLATION BOX ON THE CUSTOMER PAGE")
ex("UPDATE bookings SET status='pending', cancel_reason='' "
   "WHERE user_id=(SELECT id FROM users WHERE email=%s) LIMIT 1", (support.CUSTOMER_EMAIL,))
t = body(cus.get("/bookings", base_url=BASE))
check("a reason box is on the page", 'id="cancel-dialog"' in t)
check("it is a real dialog element", "<dialog" in t)
check("it offers ready-made reasons",
      "I no longer need this service" in t and "I found another provider" in t)
check("and a free-text note", 'id="cancel-note"' in t)
check("the cancel form carries a hidden reason field",
      'name="reason"' in t and "data-cancel-booking" in t)
check("the form still works without JavaScript",
      "onsubmit=\"return confirm(" in t)
check("the script is loaded", "cancel-reason.js" in t)
js = open(os.path.join(support.PROJECT_ROOT, "static", "js", "cancel-reason.js"),
          encoding="utf-8").read()
check("the script writes the reason into the form", 'name="reason"' in js)
check("it opens a modal", "showModal" in js)
check("it does nothing on an old browser", 'typeof dialog.showModal !== "function"' in js)

section("135. CANCELLING WITHOUT A REASON IS STILL ALLOWED")
row = q("SELECT b.id FROM bookings b JOIN users cu ON cu.id=b.user_id "
        "WHERE cu.email=%s LIMIT 1", (support.CUSTOMER_EMAIL,))[0]
ex("UPDATE bookings SET status='pending', cancel_reason='' WHERE id=%s", (row["id"],))
clear_alerts()
cus.post(f"/bookings/{row['id']}/cancel", base_url=BASE, follow_redirects=True)
check("it still cancels",
      q("SELECT status FROM bookings WHERE id=%s", (row["id"],))[0]["status"] == "cancelled")
check("the reason is simply empty",
      q("SELECT cancel_reason FROM bookings WHERE id=%s",
        (row["id"],))[0]["cancel_reason"] == "")
got = alerts("Booking Cancelled")
check("the alert leaves the reason out rather than saying 'None'",
      got and "Reason:" not in got[0]["message"], got[0]["message"] if got else "none")

section("136. ONLY ADMINS GET THESE, AND ONLY ADMINS READ THEM")
clear_alerts()
save_profile(address="Baneshwor, Kathmandu")
everyone = q("SELECT DISTINCT u.role FROM notifications n JOIN users u ON u.id=n.user_id "
             "WHERE n.title='Provider Location Updated'")
check("only administrator accounts received it",
      [r["role"] for r in everyone] == ["admin"], str(everyone))
save_profile(address=was)
clear_alerts()

check("a customer cannot read the admin area",
      cus.get("/admin/dashboard", base_url=BASE).status_code == 302)
check("the alerts page is still per-account",
      body(cus.get("/notifications", base_url=BASE)).count("Provider Location Updated") == 0)

raise SystemExit(results.report() and 1 or 0)
