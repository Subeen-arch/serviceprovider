"""The payment notice, and that the app actually behaves the way it promises."""
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
import re as _re
def body(r):
    # Collapse whitespace so a phrase split across template lines still matches.
    return " ".join(r.get_data(as_text=True).split())

NOTICE = ("Payment is not required when you submit your service request",
          "reviewed by the service provider",
          "payment option will become available",
          "complete the payment before the service can proceed",
          "rejects your request, no payment will be required")

ex("DELETE FROM bookings WHERE note LIKE 'NOTICE%'")

prov = q("SELECT p.id, p.hourly_rate, p.business_name, u.email FROM providers p "
         "JOIN users u ON u.id=p.user_id JOIN services s ON s.id=p.service_id "
         "WHERE s.name='Electrician' AND p.is_approved=1 AND p.address LIKE 'Thamel%' LIMIT 1")[0]
PID = prov["id"]
AMOUNT = float(prov["hourly_rate"]) * 2
future = (date.today() + timedelta(days=14)).isoformat()

cust = app.test_client(); login(cust, "aarati@example.com")
pv   = app.test_client(); login(pv, prov["email"])
form = {"latitude": "27.7154", "longitude": "85.3123", "address": "Thamel, Kathmandu",
        "scheduled_date": future, "scheduled_time": "12:00",
        "estimated_hours": "2", "note": "NOTICE flow"}

print("\n########## 42. NOTICE IS VISIBLE BEFORE SUBMITTING ##########")
t = body(cust.get(f"/book/{PID}?latitude=27.7154&longitude=85.3123&address=Thamel", base_url=BASE))
for phrase in NOTICE:
    check(f"booking page notice: '{phrase[:44]}...'", phrase in t)
check("booking button no longer promises payment", "Continue to review your request" in t)

t = body(cust.post(f"/book/{PID}", data=form, base_url=BASE))
for phrase in NOTICE:
    check(f"confirmation notice: '{phrase[:44]}...'", phrase in t)
check("confirmation button says 'Send service request'", "Send service request" in t)
check("confirmation does not offer to pay", "with Khalti" not in t)
check("confirmation states nothing is charged now", "Nothing is charged now" in t)

print("\n########## 43. NOTICE IS VISIBLE AFTER SUBMITTING ##########")
before_pay = q("SELECT COUNT(*) n FROM payments")[0]["n"]
r = cust.post(f"/book/{PID}/request", data=form, base_url=BASE, follow_redirects=True)
bk = q("SELECT * FROM bookings WHERE note='NOTICE flow' ORDER BY id DESC LIMIT 1")[0]
check("request created", bk["status"] == "pending")
check("NO payment row created on submit",
      q("SELECT COUNT(*) n FROM payments")[0]["n"] == before_pay)
t = body(r)
for phrase in NOTICE:
    check(f"my-bookings notice: '{phrase[:44]}...'", phrase in t)
check("tells the customer who is reviewing it",
      f"Waiting for {prov['business_name']} to answer" in t)
check("says the pay option appears after acceptance",
      "No payment is needed until they accept" in t)
check("shows 'Payment: not required yet'", "not required yet" in t)
check("no pay button while pending", f"/bookings/{bk['id']}/pay" not in t)
check("total still shown up front", "Total</span>" in t and f"Rs {AMOUNT:.0f}</strong>" in t)

print("\n########## 44. THE PROMISE IS ENFORCED SERVER-SIDE ##########")
r = cust.post(f"/bookings/{bk['id']}/pay", base_url=BASE, follow_redirects=True)
check("paying before acceptance is refused",
      "has not accepted this request yet" in body(r))
check("no payment row created by the attempt",
      q("SELECT COUNT(*) n FROM payments WHERE booking_id=%s", (bk["id"],))[0]["n"] == 0)

print("\n########## 45. AFTER ACCEPTANCE THE PAY OPTION APPEARS ##########")
r = pv.post(f"/provider/bookings/{bk['id']}/accept", base_url=BASE, follow_redirects=True)
check("provider accepts an unpaid request",
      q("SELECT status FROM bookings WHERE id=%s", (bk["id"],))[0]["status"] == "accepted")
t = body(cust.get("/bookings", base_url=BASE))
check("pay button now present", f"/bookings/{bk['id']}/pay" in t)
check("prompt explains why", "Accepted. Pay before the visit" in t)
check("notice no longer shown once nothing is pending",
      NOTICE[0] not in t or q("SELECT COUNT(*) n FROM bookings WHERE user_id=%s AND status='pending'",
                              (bk["user_id"],))[0]["n"] > 0)

print("\n########## 46. SERVICE CANNOT PROCEED UNTIL PAID ##########")
r = pv.post(f"/provider/bookings/{bk['id']}/complete", base_url=BASE, follow_redirects=True)
check("provider cannot complete an unpaid job", "has not paid for this job yet" in body(r))
check("booking still accepted",
      q("SELECT status FROM bookings WHERE id=%s", (bk["id"],))[0]["status"] == "accepted")
t = body(pv.get("/provider/bookings?status=accepted", base_url=BASE))
check("provider is told why", "Waiting for the customer to pay" in t)

ex("INSERT INTO payments (booking_id, user_id, amount, payment_method, status, paid_at) "
   "VALUES (%s, %s, %s, 'khalti', 'paid', NOW())", (bk["id"], bk["user_id"], AMOUNT))
r = pv.post(f"/provider/bookings/{bk['id']}/complete", base_url=BASE, follow_redirects=True)
check("completion works once paid",
      q("SELECT status FROM bookings WHERE id=%s", (bk["id"],))[0]["status"] == "completed")

print("\n########## 47. REJECTION COSTS THE CUSTOMER NOTHING ##########")
form2 = {**form, "scheduled_time": "13:00", "note": "NOTICE reject"}
cust.post(f"/book/{PID}/request", data=form2, base_url=BASE)
bk2 = q("SELECT * FROM bookings WHERE note='NOTICE reject' ORDER BY id DESC LIMIT 1")[0]
r = pv.post(f"/provider/bookings/{bk2['id']}/reject", base_url=BASE, follow_redirects=True)
check("rejected", q("SELECT status FROM bookings WHERE id=%s", (bk2["id"],))[0]["status"] == "rejected")
check("no payment ever existed for it",
      q("SELECT COUNT(*) n FROM payments WHERE booking_id=%s", (bk2["id"],))[0]["n"] == 0)
t = body(cust.get("/bookings", base_url=BASE))
check("customer told they were not charged", "You were not charged" in t)
r = cust.post(f"/bookings/{bk2['id']}/pay", base_url=BASE, follow_redirects=True)
check("cannot pay for a rejected request", "rejected booking cannot be paid for" in body(r))

print("\n########## 48. NOTICE WORDING IS DEFINED IN ONE PLACE ##########")
import pathlib, re
tpl = pathlib.Path(r"c:\Service_provider\templates")
partial = (tpl / "_payment_notice.html").read_text(encoding="utf-8")
check("shared partial exists and carries the wording", NOTICE[0] in partial)
copies = [str(p.relative_to(tpl)) for p in tpl.rglob("*.html")
          if p.name != "_payment_notice.html" and NOTICE[0] in p.read_text(encoding="utf-8")]
check("no page hard-codes its own copy of the wording", not copies, str(copies))
includes = [str(p.relative_to(tpl)) for p in tpl.rglob("*.html")
            if '_payment_notice.html' in p.read_text(encoding="utf-8")]
check("included by booking, confirmation and my-bookings",
      set(includes) >= {"user\\book.html", "user\\confirm.html", "user\\bookings.html"}, str(includes))

print(f"\n===== notice + flow: {len(PASS)} passed, {len(FAIL)} failed =====")
if FAIL:
    print("FAILURES:"); [print("   -", f) for f in FAIL]
