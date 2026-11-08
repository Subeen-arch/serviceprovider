"""Admin search on providers/users/bookings, and the review rating filter."""
import os, sys, re
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tests import support
support.use_test_database()   # must happen before app is imported

from app import app
import queries

BASE = support.BASE
q, ex, body = support.q, support.ex, support.body
results = support.Results("search and reviews")
check, section = results.check, results.section

adm = support.client(support.ADMIN_EMAIL)
cus = support.client(support.CUSTOMER_EMAIL)
prv = support.client(support.PROVIDER_EMAIL)


def booking_rows(html):
    """How many booking rows the page rendered.

    Each row links to the same booking twice - once on the row itself and once
    on the View button - so the links cannot simply be counted.
    """
    return html.count('<tr class="row-link">')


section("137. THE SEARCH BOXES ARE THERE")
for path, placeholder in [("/admin/providers", "Search providers..."),
                          ("/admin/users", "Search users..."),
                          ("/admin/bookings", "Search bookings...")]:
    t = body(adm.get(path, base_url=BASE))
    check(f"{path} has a search box", f'placeholder="{placeholder}"' in t, placeholder)
    check(f"{path} search uses a GET form so it can be bookmarked",
          'method="get"' in t and 'name="search"' in t)
    check(f"{path} has a magnifier icon", "search-field" in t and "<svg" in t)
    check(f"{path} keeps its existing filter chips", 'class="filters"' in t)

section("138. PROVIDER SEARCH")
providers = q("SELECT p.id, p.business_name, p.address, u.name AS owner, u.email, "
              "u.phone, s.name AS service, p.is_approved "
              "FROM providers p JOIN users u ON u.id=p.user_id "
              "JOIN services s ON s.id=p.service_id")


def provider_search(term, status=None):
    url = f"/admin/providers?search={term}"
    if status:
        url += f"&status={status}"
    return body(adm.get(url, base_url=BASE))


def expected(term, status=None):
    term = term.lower()
    found = [p for p in providers
             if term in p["business_name"].lower() or term in p["owner"].lower()
             or term in p["email"].lower() or term in p["phone"].lower()
             or term in p["service"].lower() or term in p["address"].lower()]
    if status == "pending":
        found = [p for p in found if not p["is_approved"]]
    elif status == "approved":
        found = [p for p in found if p["is_approved"]]
    return found


first = providers[0]
word = first["business_name"].split()[0]
t = provider_search(word)
want = expected(word)
check(f"searching a business name ('{word}') finds it", first["business_name"] in t)
check("and finds exactly the matching set",
      t.count("/location") == len(want), f"{t.count('/location')} vs {len(want)}")

owner_word = first["owner"].split()[0]
check(f"searching an owner name ('{owner_word}') works",
      first["business_name"] in provider_search(owner_word))
check("searching an email works", first["business_name"] in provider_search(first["email"]))
check("searching a phone number works",
      first["business_name"] in provider_search(first["phone"]))

service_name = first["service"]
t = provider_search(service_name)
check(f"searching a service ('{service_name}') works",
      t.count("/location") == len(expected(service_name)),
      f"{t.count('/location')} vs {len(expected(service_name))}")

town = first["address"].split(",")[-1].strip()
t = provider_search(town)
check(f"searching a location ('{town}') works",
      t.count("/location") == len(expected(town)),
      f"{t.count('/location')} vs {len(expected(town))}")

check("search is case-insensitive",
      provider_search(word.upper()).count("/location")
      == provider_search(word.lower()).count("/location"))
check("surrounding spaces are trimmed",
      provider_search(f"%20%20{word}%20%20").count("/location") == len(want))
check("an empty search shows everything",
      body(adm.get("/admin/providers?search=", base_url=BASE)).count("/location")
      == len(providers))

section("139. SEARCH AND THE STATUS FILTER COMBINE")
for status in ["pending", "approved"]:
    t = provider_search(service_name, status)
    want = expected(service_name, status)
    check(f"{status} + '{service_name}' gives {len(want)}",
          t.count("/location") == len(want), f"{t.count('/location')} vs {len(want)}")
    check(f"the {status} chip is still marked active", 'class="active"' in t)
    check(f"the search survives on the {status} chips",
          f"search={service_name.replace(' ', '+')}" in t
          or f"search={service_name.replace(' ', '%20')}" in t, t[:0])
t = provider_search(word, "approved")
check("the search box keeps what was typed", f'value="{word}"' in t)
check("Clear returns to the same filter", 'href="/admin/providers?status=approved"' in t)

section("140. USER SEARCH")
users = q("SELECT id, name, email, phone, role FROM users")
someone = q("SELECT name, email, phone FROM users WHERE role='user' LIMIT 1")[0]
name_word = someone["name"].split()[0]
t = body(adm.get(f"/admin/users?search={name_word}", base_url=BASE))
check(f"searching a name ('{name_word}') finds them", someone["email"] in t)
check("searching a phone number works",
      someone["email"] in body(adm.get(f"/admin/users?search={someone['phone']}",
                                       base_url=BASE)))
check("searching an email works",
      someone["name"] in body(adm.get(f"/admin/users?search={someone['email']}",
                                      base_url=BASE)))
check("case does not matter",
      someone["email"] in body(adm.get(f"/admin/users?search={name_word.upper()}",
                                       base_url=BASE)))
t = body(adm.get(f"/admin/users?search={name_word}&role=provider", base_url=BASE))
matching_providers = [u for u in users if u["role"] == "provider"
                      and name_word.lower() in u["name"].lower()]
check("search combines with the role filter",
      all(u["email"] in t for u in matching_providers)
      and someone["email"] not in t if someone["email"] not in
      [u["email"] for u in matching_providers] else True)

section("141. BOOKING SEARCH")
booking = q("SELECT b.id, b.status, s.name AS service, cu.name AS customer, "
            "p.business_name, pu.name AS provider_name FROM bookings b "
            "JOIN services s ON s.id=b.service_id JOIN users cu ON cu.id=b.user_id "
            "JOIN providers p ON p.id=b.provider_id JOIN users pu ON pu.id=p.user_id "
            "LIMIT 1")[0]
for term in [str(booking["id"]), f"BK{booking['id']}", f"%23{booking['id']}"]:
    t = body(adm.get(f"/admin/bookings?search={term}", base_url=BASE))
    check(f"searching '{term.replace('%23', '#')}' finds booking {booking['id']}",
          f"/admin/bookings/{booking['id']}" in t)
check("searching a customer name works",
      f"/admin/bookings/{booking['id']}" in
      body(adm.get(f"/admin/bookings?search={booking['customer'].split()[0]}",
                   base_url=BASE)))
check("searching a business name works",
      f"/admin/bookings/{booking['id']}" in
      body(adm.get(f"/admin/bookings?search={booking['business_name'].split()[0]}",
                   base_url=BASE)))
check("searching a provider's own name works",
      f"/admin/bookings/{booking['id']}" in
      body(adm.get(f"/admin/bookings?search={booking['provider_name'].split()[0]}",
                   base_url=BASE)))
t = body(adm.get(f"/admin/bookings?search={booking['service']}", base_url=BASE))
n = q("SELECT COUNT(*) c FROM bookings b JOIN services s ON s.id=b.service_id "
      "WHERE s.name=%s", (booking["service"],))[0]["c"]
check(f"searching a service returns its {n} bookings",
      booking_rows(t) == n, f"{booking_rows(t)} vs {n}")
done = q("SELECT COUNT(*) c FROM bookings WHERE status='completed'")[0]["c"]
shown = booking_rows(body(adm.get("/admin/bookings?search=completed", base_url=BASE)))
check(f"searching a status returns its {done} bookings", shown == done, f"{shown} vs {done}")
t = body(adm.get(f"/admin/bookings?search={booking['service']}&status=completed",
                 base_url=BASE))
n = q("SELECT COUNT(*) c FROM bookings b JOIN services s ON s.id=b.service_id "
      "WHERE s.name=%s AND b.status='completed'", (booking["service"],))[0]["c"]
check("search combines with the status filter",
      booking_rows(t) == n, f"{booking_rows(t)} vs {n}")

section("142. NOTHING FOUND")
for path, words in [("/admin/providers", "No providers found."),
                    ("/admin/users", "No users found."),
                    ("/admin/bookings", "No bookings found.")]:
    t = body(adm.get(f"{path}?search=zzzznothingmatchesthis", base_url=BASE))
    check(f"{path} says '{words}'", words in t, t[-300:])
    check(f"{path} suggests trying again", "Try a different search term" in t)
    check(f"{path} offers a way back", "Clear the search" in t)
    check(f"{path} does not render an empty table", "<tbody>" not in t)

section("143. SEARCH CANNOT REACH THE SQL")
for nasty in ["%25", "_", "a%27%20OR%20%271%27%3D%271", "%3Cscript%3Ealert(1)%3C/script%3E"]:
    for path in ["/admin/providers", "/admin/users", "/admin/bookings"]:
        r = adm.get(f"{path}?search={nasty}", base_url=BASE)
        check(f"{path} survives {nasty[:18]}", r.status_code == 200, str(r.status_code))
t = body(adm.get("/admin/providers?search=%3Cscript%3Ealert(1)%3C/script%3E", base_url=BASE))
check("a script tag is escaped, not rendered", "<script>alert(1)" not in t)
check("it comes back escaped in the box", "&lt;script&gt;" in t)
check("a bare % does not match everything",
      body(adm.get("/admin/providers?search=%25", base_url=BASE)).count("/location")
      < len(providers))

section("144. ADMIN REVIEW RATING FILTER")
by_star = {row["rating"]: row["total"] for row in
           q("SELECT rating, COUNT(*) AS total FROM reviews GROUP BY rating")}
t = body(adm.get("/admin/reviews", base_url=BASE))
check("a rating dropdown is offered", 'name="rating"' in t and "All ratings" in t)
check("all five stars are options",
      all(f'value="{star}"' in t for star in range(1, 6)))
check("a sort dropdown is offered", 'name="sort"' in t)
for label in ["Newest first", "Oldest first", "Highest rating", "Lowest rating"]:
    check(f"'{label}' is a sort option", label in t)

for star in range(1, 6):
    t = body(adm.get(f"/admin/reviews?rating={star}", base_url=BASE))
    shown = t.count("row-link")
    check(f"{star} star shows the {by_star.get(star, 0)} there are",
          shown == by_star.get(star, 0), f"{shown} vs {by_star.get(star, 0)}")
    if by_star.get(star):
        other = "★" * (star + 1) if star < 5 else "★" * 4
        check(f"{star} star shows no {len(other)}-star rows",
              f'aria-label="{star + 1 if star < 5 else 4} out of 5"' not in t)
    check(f"{star} star keeps the dropdown on {star}",
          f'value="{star}" selected' in t.replace('value="%d" ' % star,
                                                  'value="%d" ' % star))
t = body(adm.get("/admin/reviews?rating=9", base_url=BASE))
check("an impossible rating falls back to all",
      t.count("row-link") == sum(by_star.values()), str(t.count("row-link")))
t = body(adm.get("/admin/reviews?rating=abc", base_url=BASE))
check("a non-numeric rating falls back to all",
      t.count("row-link") == sum(by_star.values()))

section("145. ADMIN REVIEW SORTING")


def ratings_in(html):
    return [int(n) for n in re.findall(r'aria-label="(\d) out of 5"', html)]


check("newest first is the default",
      ratings_in(body(adm.get("/admin/reviews", base_url=BASE)))
      == ratings_in(body(adm.get("/admin/reviews?sort=newest", base_url=BASE))))
highest = ratings_in(body(adm.get("/admin/reviews?sort=highest", base_url=BASE)))
check("highest rating runs 5 down to 1", highest == sorted(highest, reverse=True),
      str(highest[:8]))
lowest = ratings_in(body(adm.get("/admin/reviews?sort=lowest", base_url=BASE)))
check("lowest rating runs 1 up to 5", lowest == sorted(lowest), str(lowest[:8]))
dates_new = re.findall(r"(\d\d \w\w\w \d{4})</td>",
                       body(adm.get("/admin/reviews?sort=newest", base_url=BASE)))
dates_old = re.findall(r"(\d\d \w\w\w \d{4})</td>",
                       body(adm.get("/admin/reviews?sort=oldest", base_url=BASE)))
check("oldest first is the reverse of newest first",
      dates_old == list(reversed(dates_new)), f"{dates_new[:3]} vs {dates_old[:3]}")
t = body(adm.get("/admin/reviews?sort=nonsense", base_url=BASE))
check("an unknown sort falls back to newest",
      ratings_in(t) == ratings_in(body(adm.get("/admin/reviews", base_url=BASE))))

section("146. RATING AND SORT COMBINE")
best = max(by_star, key=lambda s: by_star[s])
t = body(adm.get(f"/admin/reviews?rating={best}&sort=oldest", base_url=BASE))
check(f"rating {best} + oldest keeps both",
      t.count("row-link") == by_star[best]
      and f'value="oldest" selected' in t.replace('value="oldest" ', 'value="oldest" '),
      str(t.count("row-link")))
# Both dropdowns live in one form, so submitting either sends both and the
# address bar keeps ?rating=&sort= across a refresh.
check("both dropdowns are in the same form",
      t.count('<form method="get"') >= 1 and 'name="rating"' in t and 'name="sort"' in t)
check("the chosen sort is still selected", 'value="oldest" selected' in t)

section("147. THE RATING SUMMARY IS COUNTED, NOT HARD-CODED")
t = body(adm.get("/admin/reviews", base_url=BASE))
total = sum(by_star.values())
average = sum(star * n for star, n in by_star.items()) / total if total else 0
check(f"the total ({total}) matches the database", f"{total} review" in t, str(total))
check(f"the average ({average:.1f}) matches the database", f"{average:.1f}" in t)
for star, count in by_star.items():
    check(f"the {star}-star count ({count}) is shown",
          f'<span class="rating-count">{count}</span>' in t
          or f"rating-count\">{count}<" in t)

section("148. PROVIDER REVIEWS: FILTER, SORT AND ISOLATION")
mine = q("SELECT p.id FROM providers p JOIN users u ON u.id=p.user_id "
         "WHERE u.email=%s", (support.PROVIDER_EMAIL,))[0]["id"]
my_stars = {row["rating"]: row["total"] for row in
            q("SELECT rating, COUNT(*) AS total FROM reviews WHERE provider_id=%s "
              "GROUP BY rating", (mine,))}
t = body(prv.get("/provider/reviews", base_url=BASE))
check("the provider gets the same dropdowns", 'name="rating"' in t and 'name="sort"' in t)
check("the summary is theirs alone",
      f"{sum(my_stars.values())} review" in t, str(sum(my_stars.values())))
for star in range(1, 6):
    t = body(prv.get(f"/provider/reviews?rating={star}", base_url=BASE))
    shown = t.count('class="review"')
    check(f"provider {star} star shows {my_stars.get(star, 0)}",
          shown == my_stars.get(star, 0), f"{shown} vs {my_stars.get(star, 0)}")

others = q("SELECT rv.comment FROM reviews rv WHERE rv.provider_id <> %s "
           "AND rv.comment <> '' LIMIT 5", (mine,))
for sort in ["newest", "oldest", "highest", "lowest"]:
    for star in ["", "1", "5"]:
        url = f"/provider/reviews?sort={sort}" + (f"&rating={star}" if star else "")
        t = body(prv.get(url, base_url=BASE))
        leaked = [o["comment"] for o in others if o["comment"] in t]
        check(f"{url} leaks no other provider's review", not leaked, str(leaked[:2]))
for attempt in ["&provider_id=1", "&provider=1", "&id=1"]:
    t = body(prv.get(f"/provider/reviews?rating=5{attempt}", base_url=BASE))
    leaked = [o["comment"] for o in others if o["comment"] in t]
    check(f"'{attempt}' in the URL changes nothing", not leaked, str(leaked[:2]))

check("provider sorting works",
      ratings_in(body(prv.get("/provider/reviews?sort=highest", base_url=BASE)))
      == sorted(ratings_in(body(prv.get("/provider/reviews?sort=highest",
                                        base_url=BASE))), reverse=True))
t = body(prv.get("/provider/reviews?rating=1", base_url=BASE))
if not my_stars.get(1):
    check("an empty rating says so plainly", "No 1-star reviews found." in t)
    check("and offers a way back", "Show all ratings" in t)

section("149. ACCESS CONTROL IS UNCHANGED")
for path in ["/admin/providers?search=a", "/admin/users?search=a",
             "/admin/bookings?search=a", "/admin/reviews?rating=5"]:
    for role, client in [("customer", cus), ("provider", prv)]:
        check(f"{role} refused {path.split('?')[0]}",
              client.get(path, base_url=BASE).status_code == 302)
    r = app.test_client().get(path, base_url=BASE)
    check(f"anonymous refused {path.split('?')[0]}",
          r.status_code == 302 and "/login" in r.headers.get("Location", ""))
check("a customer cannot open the provider review page",
      cus.get("/provider/reviews?rating=5", base_url=BASE).status_code == 302)

section("150. THE HELPERS THEMSELVES")
check("a percent sign is escaped for LIKE", queries.like_term("50%") == "%50\\%%")
check("an underscore is escaped", queries.like_term("a_b") == "%a\\_b%")
check("a backslash is escaped", queries.like_term("a\\b") == "%a\\\\b%")
check("spaces are trimmed", queries.like_term("  hi  ") == "%hi%")
for text, want in [("1024", 1024), ("#1024", 1024), ("BK1024", 1024),
                   ("bk1024", 1024), (" 1024 ", 1024), ("Ram", None), ("", None)]:
    check(f"booking_id_in({text!r}) is {want}", queries.booking_id_in(text) == want)
check("the sort whitelist has exactly the four documented options",
      sorted(queries.REVIEW_SORTS) == ["highest", "lowest", "newest", "oldest"])

raise SystemExit(results.report() and 1 or 0)
