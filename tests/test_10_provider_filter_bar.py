"""Provider bookings status filter bar."""
import os, sys, re, html
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
    c = app.test_client(); c.post("/login", data={"email": e, "password": support.SEED_PASSWORD},
                                  base_url=BASE); return c
def body(r): return " ".join(r.get_data(as_text=True).split())

prov = q("SELECT p.id, u.email FROM providers p JOIN users u ON u.id=p.user_id "
         "WHERE p.is_approved=1 ORDER BY "
         "(SELECT COUNT(*) FROM bookings b WHERE b.provider_id=p.id) DESC LIMIT 1")[0]
PID = prov["id"]

# Spread the statuses so the counts are worth checking, remembering the
# originals so this suite leaves the database exactly as it found it.
rows = q("SELECT id, status FROM bookings WHERE provider_id=%s ORDER BY id", (PID,))
ORIGINAL = [(r["id"], r["status"]) for r in rows]
for st, row in zip(["pending", "accepted", "rejected", "cancelled"], rows):
    ex("UPDATE bookings SET status=%s WHERE id=%s", (st, row["id"]))

pv = cl(prov["email"]); cust = cl("aarati@example.com")

TAB = re.compile(r'<a class="status-tab([^"]*)" data-status="([^"]*)"\s+href="([^"]+)"([^>]*)>(.*?)</a>', re.S)
def tabs(t):
    out = {}
    for m in TAB.finditer(t):
        label = " ".join(re.sub(r"<[^>]+>", " ", m.group(5)).split())
        out[m.group(2)] = {"classes": m.group(1), "href": html.unescape(m.group(3)),
                           "attrs": m.group(4), "label": label}
    return out
def count_in(tab):
    return int(re.search(r"(\d+)$", tab["label"]).group(1))

print("\n########## 94. THE FILTER BAR ##########")
t = body(pv.get("/provider/bookings", base_url=BASE))
tb = tabs(t)
check("all six tabs render",
      list(tb) == ["", "pending", "accepted", "rejected", "completed", "cancelled"], str(list(tb)))
check("dashboard subtitle", "Manage requests and track your jobs" in t)
check("bar is a labelled nav", 'aria-label="Filter bookings by status"' in t)
check("each tab has an icon", t.count("<svg") >= 6, str(t.count("<svg")))
check("each tab has a count badge", t.count("tab-count") == 6, str(t.count("tab-count")))

print("\n########## 95. COUNTS MATCH THE DATABASE ##########")
for key, tab in tb.items():
    if key:
        n = q("SELECT COUNT(*) n FROM bookings WHERE provider_id=%s AND status=%s",
              (PID, key))[0]["n"]
    else:
        n = q("SELECT COUNT(*) n FROM bookings WHERE provider_id=%s", (PID,))[0]["n"]
    check(f"'{key or 'All'}' count = {n}", count_in(tab) == n, f"shown {count_in(tab)}")

print("\n########## 96. LINKS AND ACTIVE STATE ##########")
check("All has no status parameter", tb[""]["href"] == "/provider/bookings", tb[""]["href"])
check("All active when no status", "is-active" in tb[""]["classes"])
check("All marked aria-current", "aria-current" in tb[""]["attrs"])
for key in ["pending", "accepted", "rejected", "completed", "cancelled"]:
    check(f"{key} link built by url_for",
          tb[key]["href"] == f"/provider/bookings?status={key}", tb[key]["href"])
    tt = tabs(body(pv.get(f"/provider/bookings?status={key}", base_url=BASE)))
    check(f"{key} tab active when selected", "is-active" in tt[key]["classes"])
    check(f"All not active on {key}", "is-active" not in tt[""]["classes"])

print("\n########## 97. SEARCH IS PRESERVED ACROSS TABS ##########")
t = body(pv.get("/provider/bookings?q=Aarati", base_url=BASE))
tb2 = tabs(t)
check("every tab carries q", all("q=Aarati" in x["href"] for x in tb2.values()),
      str([x["href"] for x in tb2.values()][:3]))
check("search box keeps its value", 'value="Aarati"' in t)
t = body(pv.get("/provider/bookings?status=pending&q=Aarati", base_url=BASE))
check("status and search held together",
      'value="Aarati"' in t and "is-active" in tabs(t)["pending"]["classes"])
searched = q("SELECT COUNT(*) n FROM bookings b JOIN users u ON u.id=b.user_id "
             "WHERE b.provider_id=%s AND u.name LIKE %s", (PID, "%Aarati%"))[0]["n"]
check(f"counts respect the search ({searched})", count_in(tabs(t)[""]) == searched,
      str(count_in(tabs(t)[""])))
check("an empty q is left out of the links", "q=&" not in t and "?q=\"" not in t)

print("\n########## 98. LIST STILL FILTERS AND ACTS ##########")
for key in ["pending", "accepted", "rejected", "completed", "cancelled"]:
    t = body(pv.get(f"/provider/bookings?status={key}", base_url=BASE))
    n = q("SELECT COUNT(*) n FROM bookings WHERE provider_id=%s AND status=%s",
          (PID, key))[0]["n"]
    check(f"only {key} rows listed ({n})", t.count("Booking #") == n,
          f"{t.count('Booking #')} vs {n}")
    if n:
        check(f"{key} rows carry the matching badge", f'badge-{key}">{key}' in t)

t = body(pv.get("/provider/bookings?status=pending", base_url=BASE))
check("Accept action still there", "/accept" in t)
check("Reject action still there", "/reject" in t)
check("route-map link still there", "/provider/bookings/" in t)
t = body(pv.get("/provider/bookings?status=accepted", base_url=BASE))
check("accepted rows still offer complete or explain the wait",
      "/complete" in t or "Waiting for the customer to pay" in t)
r = pv.get("/provider/bookings?status=bogus", base_url=BASE)
check("unknown status falls back to All",
      r.status_code == 200 and "is-active" in tabs(body(r))[""]["classes"])

print("\n########## 99. ACCESS AND ISOLATION UNCHANGED ##########")
check("customer still blocked", cust.get("/provider/bookings", base_url=BASE).status_code == 302)
r = app.test_client().get("/provider/bookings", base_url=BASE)
check("anonymous still blocked", r.status_code == 302 and "/login" in r.headers.get("Location", ""))
other = q("SELECT u.email FROM providers p JOIN users u ON u.id=p.user_id "
          "WHERE p.id<>%s LIMIT 1", (PID,))[0]["email"]
op = cl(other)
mine = {b["id"] for b in q("SELECT id FROM bookings WHERE provider_id=%s", (PID,))}
t = body(op.get("/provider/bookings", base_url=BASE))
check("another provider sees none of mine",
      not [i for i in mine if f"Booking #{i} " in t])
theirs = q("SELECT COUNT(*) n FROM bookings b JOIN providers p ON p.id=b.provider_id "
           "JOIN users u ON u.id=p.user_id WHERE u.email=%s", (other,))[0]["n"]
check("their counts are their own", count_in(tabs(t)[""]) == theirs)

print("\n########## 100. STYLING PRESENT ##########")
css = open(os.path.join(support.PROJECT_ROOT, "static", "css", "style.css"),
           encoding="utf-8").read()


def rule(selector):
    """The declarations inside one CSS rule, so a test can assert on what the
    rule does rather than on the literal value someone happened to type.

    Selectors in the stylesheet are aligned with runs of spaces before the
    brace, so the match has to allow for any amount of whitespace.
    """
    found = re.search(re.escape(selector) + r"\s*\{([^}]*)\}", css)
    return found.group(1) if found else ""


for want, label in [(".status-tabs", "a container"),
                    (".status-tab:hover", "a hover state"),
                    (".status-tab.is-active", "an active state"),
                    (":focus-visible", "a keyboard focus ring"),
                    ("overflow-x: auto", "sideways scrolling on a phone"),
                    ("transition:", "transitions"),
                    ("prefers-reduced-motion", "a reduced-motion guard")]:
    check(f"CSS has {label}", want in css)
check("tabs are pill shaped", "var(--r-pill)" in rule(".status-tab"))
check("tabs are tall enough for a thumb", "min-height: 40px" in rule(".status-tab"))

# Each tab carries the colour of the status it filters to, and that hue means
# the same thing here as it does on a badge.
for st, tone in [("pending", "--warn"), ("accepted", "--brand"),
                 ("completed", "--ok"), ("rejected", "--bad"),
                 ("cancelled", "--mute")]:
    active = rule(f'.status-tab[data-status="{st}"].is-active')
    check(f"{st} tab is tinted with {tone}", tone in active, active)
    check(f"{st} badge uses the same hue", tone in rule(f".badge-{st}") or tone in css)

check("the admin chip row still has its own style", ".filters a" in css)
admin_css = open(os.path.join(support.PROJECT_ROOT, "static", "css", "admin.css"),
                 encoding="utf-8").read()
check("the admin stylesheet still tunes its tables", ".admin table" in admin_css)

print(f"\n===== provider filter bar: {len(PASS)} passed, {len(FAIL)} failed =====")
if FAIL:
    print("FAILURES:"); [print("   -", f) for f in FAIL]

# Put every booking back the way it was, so the next suite is unaffected.
for booking_id, status in ORIGINAL:
    ex("UPDATE bookings SET status=%s WHERE id=%s", (status, booking_id))
