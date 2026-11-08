"""Sidebar navigation, top-right icons and the Account dropdown."""
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
def cl(e):
    c = app.test_client()
    r = c.post("/login", data={"email": e, "password": support.SEED_PASSWORD}, base_url=BASE)
    assert r.status_code == 302, e
    return c
def body(r): return " ".join(r.get_data(as_text=True).split())

ADMIN = "admin@serviceexpert.local"
CUST  = "aarati@example.com"
PROV  = "ramesh.s@example.com"
adm, cus, prv = cl(ADMIN), cl(CUST), cl(PROV)

LINK = re.compile(r'<a class="nav-link ?([^"]*)"\s+href="([^"]+)"([^>]*)>(.*?)</a>', re.S)
def links(t):
    out = []
    for m in LINK.finditer(t):
        label = " ".join(re.sub(r"<[^>]+>", " ", m.group(4)).split())
        out.append({"classes": m.group(1), "href": m.group(2),
                    "attrs": m.group(3), "label": label})
    return out
def labels(t):
    return [re.sub(r"\s*\d+$", "", x["label"]) for x in links(t)]

print("\n########## 101. NO FLASK OR JINJA ERRORS ANYWHERE ##########")
PAGES = {
    "admin": (adm, ["/admin/dashboard", "/admin/providers", "/admin/users", "/admin/services",
                    "/admin/bookings", "/admin/payments", "/admin/reviews", "/admin/messages",
                    "/notifications", "/profile"]),
    "customer": (cus, ["/search", "/bookings", "/favourites", "/notifications",
                       "/profile", "/contact"]),
    "provider": (prv, ["/provider/dashboard", "/provider/bookings", "/provider/reviews",
                       "/provider/availability", "/provider/profile", "/notifications",
                       "/profile", "/contact"]),
}
for role, (client, paths) in PAGES.items():
    for path in paths:
        r = client.get(path, base_url=BASE)
        check(f"{role} {path} -> 200", r.status_code == 200, str(r.status_code))

first_bk = body(adm.get("/admin/bookings", base_url=BASE))
bk_id = re.search(r"/admin/bookings/(\d+)", first_bk).group(1)
check(f"admin /admin/bookings/{bk_id} -> 200",
      adm.get(f"/admin/bookings/{bk_id}", base_url=BASE).status_code == 200)
prov_bk = body(prv.get("/provider/bookings", base_url=BASE))
pb = re.search(r"/provider/bookings/(\d+)", prov_bk)
if pb:
    check(f"provider /provider/bookings/{pb.group(1)} -> 200",
          prv.get(f"/provider/bookings/{pb.group(1)}", base_url=BASE).status_code == 200)
for path in ["/", "/login", "/register", "/contact"]:
    check(f"logged-out {path} -> 200",
          app.test_client().get(path, base_url=BASE).status_code == 200)

print("\n########## 102. ADMIN SIDEBAR ##########")
t = body(adm.get("/admin/dashboard", base_url=BASE))
want = ["Overview", "Providers", "Users", "Services", "Bookings", "Payments", "Reviews", "Messages"]
got = labels(t)
check("exactly the eight admin pages, in order", got == want, str(got))
hrefs = [x["href"] for x in links(t)]
check("every item points at a real admin URL",
      hrefs == ["/admin/dashboard", "/admin/providers", "/admin/users", "/admin/services",
                "/admin/bookings", "/admin/payments", "/admin/reviews", "/admin/messages"],
      str(hrefs))
check("sidebar element present", 'class="sidebar" id="sidebar"' in t)
check("brand and role label in sidebar",
      "sidebar-brand" in t and "sidebar-role" in t and ">Admin<" in t)
check("body marked has-sidebar", "has-sidebar" in t)
check("old horizontal nav-links gone", "nav-links" not in t)
side = t[t.find('class="sidebar-nav"'):t.find("</ul>")]
check("every sidebar item has an icon", side.count("<svg") == 8, str(side.count("<svg")))
check("no Alerts item in the sidebar", "Alerts" not in side)
check("no Account item in the sidebar", "Account" not in side)
check("no Log out in the sidebar", "Log out" not in side)
check("Log out appears exactly once on the page",
      t.count("Log out") == 1, str(t.count("Log out")))
check("logout form posts to the existing route",
      'action="/logout"' in t and 'method="post"' in t)

print("\n########## 103. ACTIVE HIGHLIGHT FOLLOWS THE PAGE ##########")
for path, expect in [("/admin/dashboard", "Overview"), ("/admin/providers", "Providers"),
                     ("/admin/users", "Users"), ("/admin/services", "Services"),
                     ("/admin/bookings", "Bookings"), ("/admin/payments", "Payments"),
                     ("/admin/reviews", "Reviews"), ("/admin/messages", "Messages")]:
    ls = links(body(adm.get(path, base_url=BASE)))
    active = [re.sub(r"\s*\d+$", "", x["label"]) for x in ls if "active" in x["classes"]]
    check(f"{path} highlights {expect} only", active == [expect], str(active))
    check(f"{path} marks it aria-current",
          len([x for x in ls if "aria-current" in x["attrs"]]) == 1)
ls = links(body(adm.get(f"/admin/bookings/{bk_id}", base_url=BASE)))
active = [re.sub(r"\s*\d+$", "", x["label"]) for x in ls if "active" in x["classes"]]
check("a booking child page keeps Bookings lit", active == ["Bookings"], str(active))

print("\n########## 104. TOP-RIGHT ICONS ONLY ##########")
t = body(adm.get("/admin/dashboard", base_url=BASE))
head = t[t.find('class="top-header"'):t.find("</header>")]
check("top bar exists", 'class="top-header"' in t)
check("bell links to the existing alerts route", 'href="/notifications"' in head)
check("account opens a menu, it is not a link", 'id="accountButton"' in head
      and "<summary" in head)
check("no 'Alerts' text beside the bell", "Alerts</a>" not in head and "> Alerts" not in head)
check("no 'Account' text beside the icon", "Account</button>" not in head)
check("both are labelled for screen readers",
      'aria-label="Alerts' in head and 'aria-label="Account"' in head)
check("icons are inline SVG, not images", "<svg" in head and "<img" not in head)
check("only two action icons in the top bar",
      head.count('class="top-icon') == 2, str(head.count('class="top-icon')))
check("hamburger button present for mobile", 'class="mobile-menu-button"' in head)

print("\n########## 105. UNREAD COUNTS ##########")
c = support.connect()
cur = c.cursor(dictionary=True)
cur.execute("SELECT id FROM users WHERE email IN (%s, %s)", (CUST, PROV))
uids = [row["id"] for row in cur.fetchall()]
for uid in uids:
    cur.execute("INSERT INTO notifications (user_id, message) VALUES (%s, 'Nav test alert')",
                (uid,))
cur.execute("INSERT INTO messages (name, email, subject, body) VALUES "
            "('Nav Test', 'nav@test.local', 'Nav', 'Testing the messages badge.')")
c.commit()

# The provider's bell is an icon, so its count sits in the round red badge.
t = body(prv.get("/provider/dashboard", base_url=BASE))
check("provider bell shows a red unread badge", 'class="icon-badge"' in t)
shown = re.search(r'icon-badge">(\d+)', t)
check("provider badge count is right", shown and shown.group(1) == "1",
      shown.group(1) if shown else "none")

# The customer's bell is an icon too, so it uses the same round red badge.
t = body(cus.get("/search", base_url=BASE))
check("customer bell shows a red unread badge", 'class="icon-badge"' in t)
shown = re.search(r'icon-badge">(\d+)', t)
check("customer badge count is right", shown and shown.group(1) == "1",
      shown.group(1) if shown else "none")

t = body(adm.get("/admin/dashboard", base_url=BASE))
cur.execute("SELECT COUNT(*) n FROM messages WHERE is_read=0")
unread = cur.fetchone()["n"]
check(f"Messages item shows its own count ({unread})", f'class="nav-badge">{unread}<' in t)

cus.get("/notifications", base_url=BASE)
check("customer badge clears once alerts are read",
      "icon-badge" not in body(cus.get("/search", base_url=BASE)))
prv.get("/notifications", base_url=BASE)
check("provider badge clears once alerts are read",
      "icon-badge" not in body(prv.get("/provider/dashboard", base_url=BASE)))

print("\n########## 106. ACCOUNT DROPDOWN CONTENTS ##########")
for role, client in [("admin", adm), ("provider", prv)]:
    t = body(client.get("/profile", base_url=BASE))
    menu = t[t.find('id="accountMenu"'):t.find("</header>")]
    check(f"{role}: dropdown is a details element, closed by default",
          '<details class="menu account-dropdown">' in t and 'id="accountMenu"' in t)
    check(f"{role}: Profile in dropdown", "Profile" in menu)
    check(f"{role}: Security in dropdown", "Security" in menu)
    check(f"{role}: Log out in dropdown", "Log out" in menu)
    check(f"{role}: separator sits between Security and Log out",
          menu.find("account-sep") > menu.find("Security")
          and menu.find("account-sep") < menu.find("Log out"))
    check(f"{role}: Profile uses the existing /profile route", 'href="/profile"' in menu)
    check(f"{role}: Security jumps to the password card", 'href="/profile#security"' in menu)
    check(f"{role}: the account page has that anchor", 'id="security"' in t)
    check(f"{role}: name and email shown in the dropdown", "account-who" in menu)

print("\n########## 107. THE CUSTOMER KEEPS THE TOP BAR ##########")
TOP = re.compile(r'<a href="([^"]+)"\s+class="([^"]*)">(.*?)</a>', re.S)
def top_items(t):
    return [(" ".join(re.sub(r"<[^>]+>", " ", m.group(3)).split()), m.group(2))
            for m in TOP.finditer(t)]

t = body(cus.get("/search", base_url=BASE))
check("customer has no sidebar", 'id="sidebar"' not in t)
check("customer body is not has-sidebar", "has-sidebar" not in t)
check("customer keeps a horizontal top bar", 'class="nav-inner"' in t and "nav-links" in t)

# LEFT: brand, then the four pages in the order asked for.
check("brand comes first", t.find('class="brand"') < t.find('class="nav-links nav-main"'))
left = t[t.find('class="nav-links nav-main"'):t.find('class="nav-actions"')]
got = [label for label, _ in top_items(left)]
check("left side is brand then the four pages, in order",
      got == ["Find a service", "My bookings", "Contact", "Favourites"], str(got))
check("each page link has an icon", left.count('class="ico"') == 4, str(left.count('class="ico"')))

# RIGHT: the two icons, no text.
right = t[t.find('class="nav-actions"'):t.find("</header>")]
check("the actions group is on the right", 'class="nav-actions"' in t)
check("bell links to the existing alerts route", 'href="/notifications"' in right)
check("no 'Alerts' text beside the bell", "Alerts<" not in right)
check("no 'Account' text beside the icon", "Account<" not in right)
check("both icons are labelled for screen readers",
      'aria-label="Alerts' in right and 'aria-label="Account"' in right)
check("exactly two icons on the right",
      right.count('class="top-icon') == 2, str(right.count('class="top-icon')))
check("icons are inline SVG, not images", "<svg" in right and "<img" not in right)

# The account menu holds Manage account and Logout, and nothing else.
menu = t[t.find('id="accountMenu"'):t.find("</header>")]
check("account menu is a details element, closed by default",
      '<details class="menu account-dropdown">' in t)
check("Manage account in the menu", "Manage account" in menu)
check("it goes to the existing account page", 'href="/profile"' in menu)
check("Logout in the menu", "Logout" in menu)
check("Logout posts to the existing route", 'action="/logout"' in menu)
check("a separator between them",
      menu.find("account-sep") > menu.find("Manage account")
      and menu.find("account-sep") < menu.find("Logout"))
check("the visitor's name and email are in the menu",
      "account-who" in menu and "Aarati" in menu)
check("Logout appears exactly once on the page",
      t.count("Logout") + t.count("Log out") == 1,
      str(t.count("Logout") + t.count("Log out")))
check("no Logout outside the account menu", "btn-outline btn-sm" not in t.split("</header>")[0])

check("customer sees no admin page link", "/admin/" not in t)
check("customer sees no provider page link", "/provider/" not in t)
for path, expect in [("/search", "Find a service"), ("/bookings", "My bookings"),
                     ("/contact", "Contact"), ("/favourites", "Favourites")]:
    page = body(cus.get(path, base_url=BASE))
    left = page[page.find('class="nav-links nav-main"'):page.find('class="nav-actions"')]
    active = [label for label, cls in top_items(left) if "active" in cls]
    check(f"customer {path} highlights {expect}", active == [expect], str(active))
r = cus.get("/notifications", base_url=BASE)
check("the bell is marked current on the alerts page", "top-icon is-current" in body(r))

t = body(prv.get("/provider/dashboard", base_url=BASE))
got = labels(t)
check("provider sidebar",
      got == ["Dashboard", "Bookings", "Reviews", "Hours", "My profile", "Contact"], str(got))
check("provider sees no admin link", "/admin/" not in t)
check("provider role label", ">Service provider<" in t)
for path, expect in [("/provider/dashboard", "Dashboard"), ("/provider/bookings", "Bookings"),
                     ("/provider/reviews", "Reviews"), ("/provider/availability", "Hours"),
                     ("/provider/profile", "My profile"), ("/contact", "Contact")]:
    active = [x["label"] for x in links(body(prv.get(path, base_url=BASE)))
              if "active" in x["classes"]]
    check(f"provider {path} highlights {expect}", active == [expect], str(active))

print("\n########## 108. BACKEND SECURITY STILL ENFORCED ##########")
for path in ["/admin/dashboard", "/admin/providers", "/admin/users", "/admin/services",
             "/admin/bookings", "/admin/payments", "/admin/reviews", "/admin/messages"]:
    for role, client in [("customer", cus), ("provider", prv)]:
        r = client.get(path, base_url=BASE)
        check(f"{role} typing {path} is refused", r.status_code == 302, str(r.status_code))
    r = app.test_client().get(path, base_url=BASE)
    check(f"anonymous {path} -> /login",
          r.status_code == 302 and "/login" in r.headers.get("Location", ""))
for path in ["/provider/dashboard", "/provider/bookings", "/provider/availability"]:
    check(f"customer refused {path}", cus.get(path, base_url=BASE).status_code == 302)
check("provider refused /favourites", prv.get("/favourites", base_url=BASE).status_code == 302)
check("admin refused /search", adm.get("/search", base_url=BASE).status_code == 302)

print("\n########## 109. LOGGED-OUT PAGES KEEP THE OLD BAR ##########")
t = body(app.test_client().get("/", base_url=BASE))
check("no sidebar when signed out", 'id="sidebar"' not in t)
check("plain header still there", 'class="nav-inner"' in t)
check("Log in and Sign up still offered", ">Log in<" in t and ">Sign up<" in t)
check("no account dropdown when signed out", "accountMenu" not in t)
check("body not marked has-sidebar", "has-sidebar" not in t)

print("\n########## 110. LOGIN / LOGOUT STILL WORK ##########")
fresh = app.test_client()
r = fresh.post("/login", data={"email": PROV, "password": support.SEED_PASSWORD}, base_url=BASE)
check("login redirects to the provider dashboard",
      r.status_code == 302 and "/provider/dashboard" in r.headers["Location"],
      r.headers.get("Location"))
check("signed in, the sidebar appears",
      'id="sidebar"' in body(fresh.get("/provider/dashboard", base_url=BASE)))
r = fresh.post("/logout", base_url=BASE)
check("logout redirects", r.status_code == 302)
check("after logout the private page is refused",
      fresh.get("/provider/dashboard", base_url=BASE).status_code == 302)
r = app.test_client().post("/login", data={"email": ADMIN, "password": "wrong"}, base_url=BASE)
check("a wrong password is still rejected (401)", r.status_code == 401,
      str(r.status_code))

print("\n########## 110b. THE SEPARATE ADMINISTRATOR LOGIN ##########")
anon = app.test_client()
r = anon.get("/login", base_url=BASE)
t = body(r)
check("normal login page still loads", r.status_code == 200)
check("it offers the administrator entrance", 'href="/login/admin"' in t)
check("the link says what it is", "Log in as administrator" in t)
check("normal sign-up link untouched", 'href="/register"' in t)

r = anon.get("/login/admin", base_url=BASE)
t = body(r)
check("admin login page loads", r.status_code == 200, str(r.status_code))
check("it says it is administrators only", "for the site administrator only" in t)
check("it has email and password fields",
      'name="email"' in t and 'name="password"' in t)
check("it links back to the normal login", 'href="/login"' in t)
# The public header still carries Sign up; the admin card itself must not.
card = t[t.find('class="card admin-login"'):t.find("</main>")]
check("the admin card itself does not offer sign-up", "/register" not in card)

# A customer with the RIGHT password is still refused, because of the role test.
r = app.test_client().post("/login/admin",
                           data={"email": CUST, "password": support.SEED_PASSWORD},
                           base_url=BASE)
check("a customer cannot log in here even with a correct password",
      r.status_code == 403, str(r.status_code))
check("and is told to use the normal page", "administrators only" in body(r))
check("no session was started",
      "Set-Cookie" not in r.headers or "session=;" in r.headers.get("Set-Cookie", ""))
r = app.test_client().post("/login/admin",
                           data={"email": PROV, "password": support.SEED_PASSWORD},
                           base_url=BASE)
check("a provider cannot log in here either", r.status_code == 403, str(r.status_code))

# A wrong password gets the same generic message the normal login uses, so the
# page cannot be used to discover which addresses are administrator accounts.
r = app.test_client().post("/login/admin",
                           data={"email": ADMIN, "password": "wrong"}, base_url=BASE)
check("wrong admin password -> 401", r.status_code == 401, str(r.status_code))
check("generic message, no role hint", "Incorrect email or password" in body(r))
r = app.test_client().post("/login/admin",
                           data={"email": "nobody@example.com", "password": "wrong"},
                           base_url=BASE)
check("unknown email gets the identical message",
      r.status_code == 401 and "Incorrect email or password" in body(r))

a = app.test_client()
r = a.post("/login/admin", data={"email": ADMIN, "password": support.SEED_PASSWORD}, base_url=BASE)
check("the admin can log in here",
      r.status_code == 302 and "/admin/dashboard" in r.headers["Location"],
      r.headers.get("Location"))
check("and lands on a working dashboard with the sidebar",
      'id="sidebar"' in body(a.get("/admin/dashboard", base_url=BASE)))
r = a.get("/login/admin", base_url=BASE)
check("already signed in, it redirects instead of asking again", r.status_code == 302)
a.post("/logout", base_url=BASE)
check("logging out from here still works",
      a.get("/admin/dashboard", base_url=BASE).status_code == 302)

# The ordinary login is untouched: all three roles still use it as before.
for email, home in [(ADMIN, "/admin/dashboard"), (CUST, "/search"),
                    (PROV, "/provider/dashboard")]:
    r = app.test_client().post("/login", data={"email": email, "password": support.SEED_PASSWORD},
                               base_url=BASE)
    check(f"normal login still works for {email} -> {home}",
          r.status_code == 302 and home in r.headers["Location"], r.headers.get("Location"))

print("\n########## 111. CSS AND JAVASCRIPT ##########")
css = open(os.path.join(support.PROJECT_ROOT, "static", "css", "style.css"), encoding="utf-8").read()
for want in [".sidebar", ".sidebar-brand", ".sidebar-nav", ".nav-item", ".nav-link",
             ".nav-link.active", ".app-main", ".top-header", ".top-header-actions",
             ".top-icon", ".account-dropdown", ".mobile-menu-button"]:
    check(f"CSS defines {want}", re.search(re.escape(want) + r"[\s,{:]", css) is not None)
def rule(selector):
    """What one CSS rule actually declares.

    Asserting on the rule rather than on a literal hex value means these
    checks keep working when the palette is restyled, and still fail if the
    behaviour they protect disappears.
    """
    found = re.search(re.escape(selector) + r"\s*\{([^}]*)\}", css)
    return found.group(1) if found else ""


check("the sidebar is a dark panel", "var(--dark)" in rule(".sidebar"))
check("the active item is filled with the brand colour",
      "var(--brand)" in rule(".nav-link.active"), rule(".nav-link.active"))
check("the sidebar holds a fixed column open",
      re.search(r"width:\s*2[0-9]{2}px", rule(".sidebar")) is not None, rule(".sidebar"))
check("nav items are rounded", "border-radius" in rule(".nav-link"))
check("nav items are a 44px target", "min-height: 44px" in rule(".nav-link"))
check("hover effect defined", ".nav-link:hover" in css)
check("dropdown is absolutely positioned so it cannot move the page",
      "position: absolute" in rule(".account-menu, .row-menu-list"))
check("mobile breakpoint collapses the sidebar",
      re.search(r"@media \(max-width: \d{3}px\)", css) is not None
      and "translateX(-100%)" in css)
check("reduced motion respected", "prefers-reduced-motion" in css)

admin_css = open(os.path.join(support.PROJECT_ROOT, "static", "css", "admin.css"), encoding="utf-8").read()
check("no dead admin header rules", ".admin .nav" not in admin_css)
check("the admin sheet only tunes the admin area",
      all(line.strip().startswith((".admin", "/*", "*", "@media", "}", ""))
          for line in admin_css.splitlines()),
      "admin.css should only contain .admin rules")
check("admin tables are tuned for density", ".admin table" in admin_css)
check("filter chips are in the shared system", ".filters" in css)
check("the status strip is in the shared system", ".status-strip" in css)
js = open(os.path.join(support.PROJECT_ROOT, "static", "js", "nav.js"), encoding="utf-8").read()
for want in ["details.menu", "menuButton", "sidebarBackdrop", "contains(event.target)",
             "Escape", "aria-expanded"]:
    check(f"nav.js handles {want}", want in js)
check("only one menu open at a time", "closeMenus" in js)
check("no framework pulled in", "jquery" not in js.lower() and "react" not in js.lower())
base = open(os.path.join(support.PROJECT_ROOT, "templates", "base.html"), encoding="utf-8").read()
check("nav.js is loaded by the layout", "js/nav.js" in base)
check("password eye script still loaded", "password-toggle.js" in base)
check("sidebar markup lives in one partial only", base.count("_sidebar.html") == 1)

print("\n########## 112. THE REST OF THE APP IS UNTOUCHED ##########")
t = body(prv.get("/provider/bookings", base_url=BASE))
check("provider status filter bar still there", 'aria-label="Filter bookings by status"' in t)
check("status tab counts still render", t.count("tab-count") == 6, str(t.count("tab-count")))
t = body(cus.get("/bookings", base_url=BASE))
check("customer booking search still there", 'name="q"' in t)
t = body(adm.get("/admin/bookings", base_url=BASE))
check("admin filter chips still there", 'class="filters"' in t)
t = body(cus.get("/search", base_url=BASE))
check("recommendation modes still offered", "best_overall" in t)
r = cus.post("/profile", data={"name": "Aarati Shrestha", "phone": "9801000001"},
             base_url=BASE, follow_redirects=True)
check("profile save still works", "Profile updated" in body(r))
r = cus.post("/profile/password", data={"current_password": "wrong",
                                        "new_password": "Newpass123",
                                        "confirm_password": "Newpass123"},
             base_url=BASE, follow_redirects=True)
check("password change still validates", "current password is not correct" in body(r))

cur.execute("DELETE FROM notifications WHERE message='Nav test alert'")
cur.execute("DELETE FROM messages WHERE email='nav@test.local'")
c.commit(); cur.close(); c.close()

print(f"\n===== navigation: {len(PASS)} passed, {len(FAIL)} failed =====")
if FAIL:
    print("FAILURES:")
    for f in FAIL:
        print("   -", f)
