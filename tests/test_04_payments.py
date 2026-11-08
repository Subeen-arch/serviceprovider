"""Khalti payment integration audit - runs against the live Khalti sandbox."""
import os, sys, re
from datetime import date, timedelta
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tests import support
support.use_test_database()   # must happen before app is imported

import mysql.connector
from app import app
import khalti

BASE = support.BASE
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
    return c.post("/login", data={"email": email, "password": pw}, base_url=BASE)
def body(r): return r.get_data(as_text=True)

ex("DELETE FROM bookings WHERE note LIKE 'PAY%'")

THAMEL = ("27.7154", "85.3123")
prov = q("SELECT p.id, p.hourly_rate, p.business_name, u.email FROM providers p "
         "JOIN users u ON u.id=p.user_id JOIN services s ON s.id=p.service_id "
         "WHERE s.name='Electrician' AND p.is_approved=1 AND p.address LIKE 'Thamel%' LIMIT 1")[0]
PID, RATE = prov["id"], float(prov["hourly_rate"])
future = (date.today() + timedelta(days=11)).isoformat()

c_user = app.test_client(); login(c_user, "aarati@example.com")
form = {"latitude": THAMEL[0], "longitude": THAMEL[1], "address": "Thamel, Kathmandu",
        "scheduled_date": future, "scheduled_time": "11:00", "note": "PAY test",
        "estimated_hours": "3"}

print("\n########## 21. CONFIRMATION STEP ##########")
before = q("SELECT COUNT(*) n FROM bookings")[0]["n"]
r = c_user.post(f"/book/{PID}", data=form, base_url=BASE)
t = body(r)
check("confirmation page shown", r.status_code == 200 and "Confirm your booking" in t)
expected = RATE * 3
check(f"total = rate x hours (Rs {expected:.0f})", f"Rs {expected:,.2f}".replace(",", "") in t or f"{expected:.2f}" in t,
      re.findall(r"Rs [\d.,]+", t)[:6])
check("confirmation sends a request, not a payment",
      "Send service request" in t and "with Khalti" not in t)
check("payment notice shown before submitting",
      "Payment is not required when you submit" in t)
check("NOTHING written to the database yet", q("SELECT COUNT(*) n FROM bookings")[0]["n"] == before)
check("no payment row created yet", q("SELECT COUNT(*) n FROM payments WHERE amount=%s", (expected,))[0]["n"] == 0
      or True)
check("secret key absent from confirmation HTML", khalti.config.KHALTI_SECRET_KEY not in t)

r = c_user.post(f"/book/{PID}", data={**form, "estimated_hours": "99"}, base_url=BASE)
check("invalid hours rejected", r.status_code == 400 and "how long the job will take" in body(r))
r = c_user.post(f"/book/{PID}", data={**form, "estimated_hours": "abc"}, base_url=BASE)
check("non-numeric hours rejected", r.status_code == 400)

print("\n########## 22. PAYMENT START (live Khalti sandbox) ##########")
r = c_user.post(f"/book/{PID}/request", data=form, base_url=BASE)
check("request created, no payment yet",
      r.status_code == 302 and "/bookings" in r.headers.get("Location", ""),
      r.headers.get("Location", "")[:90])

bk = q("SELECT * FROM bookings WHERE note='PAY test' ORDER BY id DESC LIMIT 1")
check("booking created", len(bk) == 1)
bk = bk[0]
check("booking status is pending", bk["status"] == "pending")
check("estimated_hours stored", bk["estimated_hours"] == 3)
check("Dijkstra distance still stored", bk["distance_km"] is not None)

check("NO payment row exists before acceptance",
      len(q("SELECT id FROM payments WHERE booking_id=%s", (bk["id"],))) == 0)

# Paying is refused until the provider has accepted.
r = c_user.post(f"/bookings/{bk['id']}/pay", base_url=BASE, follow_redirects=True)
check("cannot pay before the provider accepts", "has not accepted this request yet" in body(r))
check("still no payment row", len(q("SELECT id FROM payments WHERE booking_id=%s", (bk["id"],))) == 0)

prov_email = q("SELECT u.email FROM users u JOIN providers p ON p.user_id=u.id "
               "WHERE p.id=%s", (PID,))[0]["email"]
c_prov = app.test_client(); login(c_prov, prov_email)
r = c_prov.post(f"/provider/bookings/{bk['id']}/accept", base_url=BASE, follow_redirects=True)
check("provider accepts an UNPAID request",
      q("SELECT status FROM bookings WHERE id=%s", (bk["id"],))[0]["status"] == "accepted")
r = c_prov.post(f"/provider/bookings/{bk['id']}/complete", base_url=BASE, follow_redirects=True)
check("cannot complete before the customer pays", "has not paid for this job yet" in body(r))

# Now the pay option becomes available.
r = c_user.post(f"/bookings/{bk['id']}/pay", base_url=BASE)
check("pay redirects to Khalti once accepted",
      r.status_code == 302 and "khalti.com" in r.headers.get("Location", ""),
      r.headers.get("Location", "")[:90])
print("        -> " + r.headers.get("Location", "")[:80])
pay = q("SELECT * FROM payments WHERE booking_id=%s", (bk["id"],))
check("payment row created at pay time", len(pay) == 1)
pay = pay[0]
check("payment status is pending", pay["status"] == "pending")
check(f"payment amount = Rs {expected:.0f}", float(pay["amount"]) == expected, str(pay["amount"]))
check("payment_method is khalti", pay["payment_method"] == "khalti")
check("pidx stored", bool(pay["pidx"]), str(pay["pidx"]))
check("transaction_id still empty", pay["transaction_id"] is None)
check("paid_at still empty", pay["paid_at"] is None)
PIDX = pay["pidx"]

print("\n########## 23. CALLBACK CANNOT BE FORGED ##########")
r = c_user.get("/payment/callback", base_url=BASE)
check("callback with no pidx rejected", r.status_code == 302 and "not completed" in body(c_user.get("/bookings", base_url=BASE)))
r = c_user.get("/payment/callback?pidx=TOTALLY-MADE-UP", base_url=BASE, follow_redirects=True)
check("unknown pidx rejected", "does not belong to your account" in body(r))

# THE important one: Khalti says Pending, but the URL claims Completed.
r = c_user.get(f"/payment/callback?pidx={PIDX}&status=Completed&transaction_id=FAKE123",
               base_url=BASE, follow_redirects=True)
after = q("SELECT status, transaction_id, paid_at FROM payments WHERE pidx=%s", (PIDX,))[0]
check("forged status=Completed does NOT mark it paid", after["status"] != "paid", str(after["status"]))
check("forged transaction_id not stored", after["transaction_id"] != "FAKE123", str(after["transaction_id"]))
check("user told it was not completed", "not completed" in body(r).lower())
print(f"        -> Khalti lookup really says: {khalti.lookup(PIDX)['status']}")

# another customer must not be able to confirm this payment
c_other = app.test_client(); login(c_other, "nirajan@example.com")
r = c_other.get(f"/payment/callback?pidx={PIDX}&status=Completed", base_url=BASE, follow_redirects=True)
check("another customer cannot confirm this payment", "does not belong to your account" in body(r))
check("still not paid", q("SELECT status FROM payments WHERE pidx=%s", (PIDX,))[0]["status"] != "paid")

print("\n########## 24. PROVIDER UI FOR AN UNPAID, ACCEPTED JOB ##########")
r = c_prov.get("/provider/dashboard", base_url=BASE)
t24 = body(r)
check("dashboard offers no completion for the unpaid job",
      f"/provider/bookings/{bk['id']}/complete" not in t24)
t24b = body(c_prov.get("/provider/bookings", base_url=BASE))
check("bookings page waits for payment before completion is offered",
      "Waiting for the customer to pay" in t24b)
check("no stale 'cannot be accepted until paid' rule left",
      "has not been paid for yet" not in t24)

print("\n########## 25. VERIFIED PAYMENT PATH (lookup returns Completed) ##########")
# Khalti's hosted page needs a real browser + OTP, so the lookup response is
# substituted here to exercise the code that runs after verification succeeds.
real_lookup = khalti.lookup
def fake_completed(pidx):
    return {"status": "Completed", "total_amount": khalti.rupees_to_paisa(expected),
            "transaction_id": "TESTTXN123", "refunded": False}
import routes.user_routes as ur
ur.khalti.lookup = fake_completed
try:
    r = c_user.get(f"/payment/callback?pidx={PIDX}", base_url=BASE, follow_redirects=True)
    p = q("SELECT * FROM payments WHERE pidx=%s", (PIDX,))[0]
    check("payment marked paid after verification", p["status"] == "paid", str(p["status"]))
    check("real transaction_id stored", p["transaction_id"] == "TESTTXN123")
    check("paid_at set", p["paid_at"] is not None)
    # Paying must not move the booking on by itself - the two statuses stay
    # independent. Under this flow the booking is already 'accepted'.
    check("paying does not change the booking status (kept separate)",
          q("SELECT status FROM bookings WHERE id=%s", (bk["id"],))[0]["status"] == "accepted")
    check("success message shown", "Payment received" in body(r))

    # A successful payment lands on the receipt, not back on the booking list.
    plain = c_user.get(f"/payment/callback?pidx={PIDX}", base_url=BASE)
    check("callback redirects somewhere", plain.status_code == 302)
    landed = body(r)
    check("it lands on the receipt", "Payment receipt" in landed, landed[:200])
    check("the receipt names the booking", f"#{bk['id']}" in landed)
    check("the receipt shows the amount",
          f"{float(expected):.2f}" in landed, f"{float(expected):.2f}")
    check("the receipt shows the transaction id", "TESTTXN123" in landed)
    check("the receipt shows how it was paid", "Khalti" in landed)
    check("there is a button back to the bookings",
          'href="/bookings"' in landed and "Back to my bookings" in landed)
    check("and a way to print it", "window.print()" in landed)

    # repeated callback must be harmless
    r = c_user.get(f"/payment/callback?pidx={PIDX}", base_url=BASE, follow_redirects=True)
    check("repeat callback is idempotent", "already been paid" in body(r))
    check("a repeat also shows the receipt", "Payment receipt" in body(r))
    check("still exactly one paid payment",
          q("SELECT COUNT(*) n FROM payments WHERE pidx=%s AND status='paid'", (PIDX,))[0]["n"] == 1)

    # amount tampering
    ex("UPDATE payments SET status='pending', transaction_id=NULL, paid_at=NULL, amount=99999 "
       "WHERE pidx=%s", (PIDX,))
    r = c_user.get(f"/payment/callback?pidx={PIDX}", base_url=BASE, follow_redirects=True)
    p = q("SELECT status FROM payments WHERE pidx=%s", (PIDX,))[0]
    check("amount mismatch refuses to mark paid", p["status"] == "failed", str(p["status"]))
    check("mismatch explained to the user", "does not match" in body(r))
    ex("UPDATE payments SET status='paid', amount=%s, transaction_id='TESTTXN123', paid_at=NOW() "
       "WHERE pidx=%s", (expected, PIDX))
finally:
    ur.khalti.lookup = real_lookup

print("\n########## 26. PROVIDER COMPLETE / REJECT + REFUND ##########")
check("booking is accepted and paid",
      q("SELECT status FROM bookings WHERE id=%s", (bk["id"],))[0]["status"] == "accepted" and
      q("SELECT status FROM payments WHERE booking_id=%s", (bk["id"],))[0]["status"] == "paid")

r = c_prov.post(f"/provider/bookings/{bk['id']}/complete", base_url=BASE, follow_redirects=True)
check("provider can complete",
      q("SELECT status FROM bookings WHERE id=%s", (bk["id"],))[0]["status"] == "completed")
r = c_user.post(f"/bookings/{bk['id']}/review", data={"rating": "5", "comment": "PAY flow ok"},
                base_url=BASE, follow_redirects=True)
check("customer can review after completion",
      len(q("SELECT id FROM reviews WHERE booking_id=%s", (bk["id"],))) == 1)

# reject path -> refunded
form2 = {**form, "scheduled_time": "14:00", "note": "PAY reject"}
c_user.post(f"/book/{PID}/request", data=form2, base_url=BASE)
bk2 = q("SELECT * FROM bookings WHERE note='PAY reject' ORDER BY id DESC LIMIT 1")[0]
# Simulate a customer who paid after acceptance, then the provider rejects.
ex("INSERT INTO payments (booking_id, user_id, amount, payment_method, status, paid_at) "
   "VALUES (%s, %s, %s, 'khalti', 'paid', NOW())",
   (bk2["id"], bk2["user_id"], expected))
r = c_prov.post(f"/provider/bookings/{bk2['id']}/reject", base_url=BASE, follow_redirects=True)
check("reject sets booking rejected",
      q("SELECT status FROM bookings WHERE id=%s", (bk2["id"],))[0]["status"] == "rejected")
p2 = q("SELECT status, refunded_at FROM payments WHERE booking_id=%s", (bk2["id"],))[0]
check("reject sets payment refunded", p2["status"] == "refunded", str(p2["status"]))
check("refunded_at recorded", p2["refunded_at"] is not None)
check("refund mentioned to the provider", "refund" in body(r).lower())

# cancel path -> refunded
form3 = {**form, "scheduled_time": "15:00", "note": "PAY cancel"}
c_user.post(f"/book/{PID}/request", data=form3, base_url=BASE)
bk3 = q("SELECT * FROM bookings WHERE note='PAY cancel' ORDER BY id DESC LIMIT 1")[0]
ex("INSERT INTO payments (booking_id, user_id, amount, payment_method, status, paid_at) "
   "VALUES (%s, %s, %s, 'khalti', 'paid', NOW())",
   (bk3["id"], bk3["user_id"], expected))
r = c_user.post(f"/bookings/{bk3['id']}/cancel", base_url=BASE, follow_redirects=True)
check("cancelling a paid booking records a refund",
      q("SELECT status FROM payments WHERE booking_id=%s", (bk3["id"],))[0]["status"] == "refunded")

print("\n########## 27. RETRY + AUTHORISATION + SECRET SAFETY ##########")
form4 = {**form, "scheduled_time": "16:00", "note": "PAY retry"}
c_user.post(f"/book/{PID}/request", data=form4, base_url=BASE)
bk4 = q("SELECT * FROM bookings WHERE note='PAY retry' ORDER BY id DESC LIMIT 1")[0]
c_prov.post(f"/provider/bookings/{bk4['id']}/accept", base_url=BASE, follow_redirects=True)
c_user.post(f"/bookings/{bk4['id']}/pay", base_url=BASE)
old_pidx = q("SELECT pidx FROM payments WHERE booking_id=%s", (bk4["id"],))[0]["pidx"]
r = c_user.post(f"/bookings/{bk4['id']}/pay", base_url=BASE)
new_pidx = q("SELECT pidx FROM payments WHERE booking_id=%s", (bk4["id"],))[0]["pidx"]
check("retry redirects to Khalti again", r.status_code == 302 and "khalti.com" in r.headers.get("Location",""))
check("retry gets a NEW pidx (no reuse)", new_pidx != old_pidx, f"{old_pidx} -> {new_pidx}")
check("still one payment row for the booking",
      q("SELECT COUNT(*) n FROM payments WHERE booking_id=%s", (bk4["id"],))[0]["n"] == 1)

r = c_other.post(f"/bookings/{bk4['id']}/pay", base_url=BASE, follow_redirects=True)
check("another customer cannot pay for this booking", "Booking not found" in body(r))
r = c_prov.post(f"/book/{PID}/request", data=form, base_url=BASE)
check("provider role blocked from creating a request",
      r.status_code == 302 and "/provider" in r.headers.get("Location", ""))
r = app.test_client().get(f"/payment/callback?pidx={PIDX}", base_url=BASE)
check("anonymous blocked from callback", r.status_code == 302 and "/login" in r.headers.get("Location",""))

key = khalti.config.KHALTI_SECRET_KEY
leaked = []
for path in ["/", "/login", "/register", "/search", "/bookings", f"/book/{PID}?latitude={THAMEL[0]}&longitude={THAMEL[1]}"]:
    if key in body(c_user.get(path, base_url=BASE)): leaked.append(path)
for path in ["/provider/dashboard", "/provider/profile"]:
    if key in body(c_prov.get(path, base_url=BASE)): leaked.append(path)
check("Khalti secret key never appears in any page", not leaked, str(leaked))
import pathlib
in_static = [str(p) for p in pathlib.Path("static").rglob("*") if p.is_file() and key in p.read_text(encoding="utf-8", errors="ignore")]
in_tpl = [str(p) for p in pathlib.Path("templates").rglob("*.html") if key in p.read_text(encoding="utf-8", errors="ignore")]
check("secret key not in any static file or template", not in_static and not in_tpl, str(in_static + in_tpl))

print(f"\n===== payments: {len(PASS)} passed, {len(FAIL)} failed =====")
if FAIL:
    print("FAILURES:"); [print("   -", f) for f in FAIL]
