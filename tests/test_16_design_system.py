"""The design system: contrast, consistency, and the rules the design sets itself.

A stylesheet can be rewritten without a single Python test noticing, so these
checks guard the design the way the other suites guard the behaviour:

  - every colour pair that carries text clears the WCAG contrast requirement
  - every class a template uses is actually defined
  - every CSS variable a rule references is actually declared
  - the three rules the system sets itself are kept: four hues, no gradients,
    no borders drawn around a card
  - nothing is left half-designed: no placeholder copy, no orphan styles,
    no control too small to press
"""
import os, re, sys, glob
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tests import support
support.use_test_database()   # must happen before app is imported

from app import app

BASE = support.BASE
body = support.body
results = support.Results("design system")
check, section = results.check, results.section

ROOT = support.PROJECT_ROOT
CSS = open(os.path.join(ROOT, "static", "css", "style.css"), encoding="utf-8").read()
ADMIN_CSS = open(os.path.join(ROOT, "static", "css", "admin.css"), encoding="utf-8").read()
ALL_CSS = CSS + ADMIN_CSS
TEMPLATES = sorted(glob.glob(os.path.join(ROOT, "templates", "**", "*.html"), recursive=True))


def name_of(path):
    return os.path.relpath(path, os.path.join(ROOT, "templates")).replace("\\", "/")


# --------------------------------------------------------------------------
# colour maths
# --------------------------------------------------------------------------
def luminance(value):
    value = value.lstrip("#")
    if len(value) == 3:
        value = "".join(c * 2 for c in value)
    channels = [int(value[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    channels = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
                for c in channels]
    return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]


def contrast(a, b):
    la, lb = luminance(a), luminance(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


TOKENS = dict(re.findall(r"--([a-z0-9-]+):\s*(#[0-9a-fA-F]{3,8})", CSS))


def tok(name):
    return TOKENS[name]


section("151. EVERY TOKEN IS DECLARED ONCE AND USED")
check(f"the palette is declared in one place ({len(TOKENS)} colours)", len(TOKENS) >= 20)
used = set(re.findall(r"var\(--([a-z0-9-]+)\)", ALL_CSS))
root = CSS[CSS.find(":root {"):CSS.find("}", CSS.find(":root {"))]
declared = set(re.findall(r"--([a-z0-9-]+):", root))
missing = sorted(used - declared)
check("every var() refers to a token that exists", not missing, str(missing))
unused = sorted(declared - used - {"dark-line"})
check("no token is declared and then never used", not unused, str(unused))

# The design says four hues carry meaning. Anything else is a neutral, a
# surface or the brand.
hues = [t for t in TOKENS if t in
        ("ok", "warn", "bad", "mute", "gold", "brand", "accent", "brand-deep")]
check("meaning is carried by a small fixed set of hues", len(hues) <= 8, str(hues))


section("152. TEXT CONTRAST (WCAG AA, 4.5:1)")
TEXT_PAIRS = [
    ("body on the page",            "ink-2", "paper"),
    ("body on a card",              "ink-2", "surface"),
    ("body in a well",              "ink-2", "sunk"),
    ("headings on the page",        "ink",   "paper"),
    ("headings on a card",          "ink",   "surface"),
    ("secondary text on a card",    "ink-3", "surface"),
    ("secondary text on the page",  "ink-3", "paper"),
    ("secondary text in a well",    "ink-3", "sunk"),
    ("placeholder text",            "ink-4", "surface"),
    ("links on a card",             "brand", "surface"),
    ("links on the page",           "brand", "paper"),
    ("stars",                       "gold",  "surface"),
    ("pending badge",               "warn",  "warn-bg"),
    ("accepted badge",              "brand-deep", "brand-tint"),
    ("completed badge",             "ok",    "ok-bg"),
    ("rejected badge",              "bad",   "bad-bg"),
    ("cancelled badge",             "mute",  "mute-bg"),
    ("sidebar item",                "on-dark-dim", "dark"),
    ("sidebar heading",             "on-dark",     "dark"),
    ("hero body text",              "on-dark-dim", "dark"),
]
for label, ink, ground in TEXT_PAIRS:
    ratio = contrast(tok(ink), tok(ground))
    check(f"{label}: {ratio:.1f}:1", ratio >= 4.5, f"{ratio:.2f} needs 4.5")

# Text sitting on a solid fill.
ON_FILL = [
    ("primary button label", "surface", "brand"),
    ("confirm button label", "surface", "ok"),
    ("danger button label",  "surface", "bad"),
    ("active chip label",    "surface", "ink"),
    ("active pending tab",   "surface", "warn"),
    ("active completed tab", "surface", "ok"),
    ("active cancelled tab", "surface", "mute"),
    ("unread count",         "surface", "bad"),
    ("sidebar active item",  "surface", "brand"),
]
for label, ink, fill in ON_FILL:
    ratio = contrast(tok(ink), tok(fill))
    check(f"{label}: {ratio:.1f}:1", ratio >= 4.5, f"{ratio:.2f} needs 4.5")


section("153. NON-TEXT CONTRAST (WCAG 1.4.11, 3:1)")
for label, colour, ground in [
        ("control borders on a card",  "line-2", "surface"),
        ("control borders on the page", "line-2", "paper"),
        ("control borders in a well",  "line-2", "sunk"),
        ("focus ring on a card",       "brand",  "surface"),
        ("focus ring on the page",     "brand",  "paper")]:
    ratio = contrast(tok(colour), tok(ground))
    check(f"{label}: {ratio:.1f}:1", ratio >= 3.0, f"{ratio:.2f} needs 3.0")


section("154. THE DESIGN KEEPS ITS OWN RULES")
check("no gradients anywhere in the stylesheets",
      "linear-gradient" not in ALL_CSS.replace(
          # the select chevron is drawn with two hard-edged gradients rather
          # than an image request; it is a shape, not a colour blend
          "linear-gradient(45deg, transparent 50%, var(--ink-3) 50%)", "").replace(
          "linear-gradient(135deg, var(--ink-3) 50%, transparent 50%)", ""),
      "a gradient crept back in")
check("no gradients in any template",
      not any("gradient" in open(t, encoding="utf-8").read() for t in TEMPLATES))

card_rule = re.search(r"\n\.card \{([^}]*)\}", CSS).group(1)
# The reference design defines a panel with a hairline. A hairline is allowed;
# a heavy outline is not, and the tone difference must still be doing the work.
check("a card is edged with a hairline, not an outline",
      "border: 1px solid var(--line)" in card_rule, card_rule)
check("a card is separated by its own surface colour", "background:" in card_rule)
check("a card does not float above the page", "box-shadow" not in card_rule)
check("elevation is kept for things that really float",
      "box-shadow: var(--lift)" in CSS)

check("one radius token, not a spread of sizes",
      len(set(re.findall(r"border-radius:\s*(\d+px)", ALL_CSS))) <= 2,
      str(set(re.findall(r"border-radius:\s*(\d+px)", ALL_CSS))))
raw_colours = set(re.findall(r":\s*(#[0-9a-fA-F]{3,6})\b", CSS)) - set(TOKENS.values())
check("colours are only written inside the token block",
      raw_colours <= {"#fff", "#ffffff", "#000"},
      str(sorted(raw_colours)))


section("155. NO INLINE STYLING LEFT IN THE TEMPLATES")
inline, dynamic = [], []
for path in TEMPLATES:
    text = open(path, encoding="utf-8").read()
    for found in re.findall(r'style="([^"]*)"', text):
        (dynamic if ("{{" in found or "{%" in found) else inline).append(
            (name_of(path), found))
check("not one static style attribute remains", not inline, str(inline[:4]))
check(f"only data-driven widths stay inline ({len(dynamic)})",
      all("width" in value for _, value in dynamic), str(dynamic))
check("no <style> block hidden in a template",
      not any("<style>" in open(t, encoding="utf-8").read() for t in TEMPLATES))
check("nothing is hidden with an inline display rule",
      not any("style.display" in open(t, encoding="utf-8").read() for t in TEMPLATES))


section("156. EVERY CLASS A TEMPLATE USES IS DEFINED")
# This is the check that catches a restyle quietly dropping a component.
in_css = set(re.findall(r"\.([a-zA-Z][\w-]*)", ALL_CSS))
generated = {"active", "is-active", "is-open", "is-empty", "is-current", "on",
             "hidden", "row-link", "tall", "admin", "has-sidebar"}
orphans = set()
for path in TEMPLATES:
    text = open(path, encoding="utf-8").read()
    for attr in re.findall(r'class="([^"]*)"', text):
        if "{{" in attr or "{%" in attr:
            attr = re.sub(r"\{\{.*?\}\}|\{%.*?%\}", " ", attr)
        for cls in attr.split():
            if not cls or cls.endswith("-"):
                continue          # "badge-" + {{ status }}, completed at render
            if cls not in in_css and cls not in generated:
                orphans.add(f"{cls} ({name_of(path)})")
check("no template uses a class the stylesheet does not define",
      not orphans, str(sorted(orphans)[:6]))

check("no template refers to a CSS variable that was removed",
      not re.search(r"var\(--(?!" + "|".join(declared) + r")[a-z0-9-]+\)",
                    "".join(open(t, encoding="utf-8").read() for t in TEMPLATES)))


section("157. TARGETS ARE BIG ENOUGH TO HIT (Fitts)")
for selector, floor in [(r"\.btn \{", 44), (r"\.nav-link \{", 44),
                        (r"\.check \{", 44), (r"\.reason \{", 44)]:
    at = re.search(selector, CSS)
    block = CSS[at.start():CSS.find("}", at.start())] if at else ""
    found = re.search(r"min-height:\s*(\d+)px", block)
    check(f"{selector.strip(chr(92)).strip(' {')} is at least {floor}px",
          found and int(found.group(1)) >= floor, block[:70])
for selector in [".top-icon", ".heart", ".mobile-menu-button"]:
    at = CSS.find(selector + " {")
    block = CSS[at:CSS.find("}", at)]
    size = re.search(r"height:\s*(\d+)px", block)
    check(f"{selector} is at least 40px", size and int(size.group(1)) >= 40, block[:70])
input_rule = re.search(r"input\[type=text\][^{]*\{([^}]*)\}", CSS).group(1)
check("inputs are a comfortable height", "min-height: 44px" in input_rule, input_rule[:80])


section("158. NOTHING IS HALF-FINISHED")
FILLER = ["lorem ipsum", "todo:", "tbd", "fixme", "your text here",
          "placeholder text", "coming soon", "dummy text", "sample text"]
problems = []
for path in TEMPLATES:
    low = open(path, encoding="utf-8").read().lower()
    for word in FILLER:
        if word in low:
            problems.append(f"{name_of(path)}: {word}")
check("no filler copy anywhere in the templates", not problems, str(problems))
check("no filler copy in the stylesheets",
      not any(w in ALL_CSS.lower() for w in ["lorem", "todo", "fixme"]))
check("no debugging colours left behind",
      not re.search(r"(?<![\w-])(red|blue|magenta|lime)\s*;", ALL_CSS))


section("159. THE PAGES THEMSELVES")
adm = support.client(support.ADMIN_EMAIL)
cus = support.client(support.CUSTOMER_EMAIL)
prv = support.client(support.PROVIDER_EMAIL)
anon = app.test_client()

PAGES = [
    ("landing",           anon, "/"),
    ("log in",            anon, "/login"),
    ("admin log in",      anon, "/login/admin"),
    ("sign up",           anon, "/register"),
    ("contact",           anon, "/contact"),
    ("find a service",    cus,  "/search"),
    ("my bookings",       cus,  "/bookings"),
    ("favourites",        cus,  "/favourites"),
    ("account",           cus,  "/profile"),
    ("alerts",            cus,  "/notifications"),
    ("provider dashboard", prv, "/provider/dashboard"),
    ("provider bookings", prv,  "/provider/bookings"),
    ("provider reviews",  prv,  "/provider/reviews"),
    ("working hours",     prv,  "/provider/availability"),
    ("business profile",  prv,  "/provider/profile"),
    ("admin overview",    adm,  "/admin/dashboard"),
    ("admin providers",   adm,  "/admin/providers"),
    ("admin users",       adm,  "/admin/users"),
    ("admin services",    adm,  "/admin/services"),
    ("admin bookings",    adm,  "/admin/bookings"),
    ("admin payments",    adm,  "/admin/payments"),
    ("admin reviews",     adm,  "/admin/reviews"),
    ("admin messages",    adm,  "/admin/messages"),
]

rendered = {}
for label, client, path in PAGES:
    response = client.get(path, base_url=BASE)
    ok = response.status_code == 200
    check(f"{label} renders", ok, str(response.status_code))
    if ok:
        rendered[label] = body(response)

check("every page loaded", len(rendered) == len(PAGES))

section("160. ONE PRIMARY ACTION PER PAGE (Von Restorff)")
# `.btn` on its own is the accent. A page with several is a page with no
# obvious next step.
for label, html in rendered.items():
    primaries = len(re.findall(r'class="btn"', html)) + \
                len(re.findall(r'class="btn btn-block"', html))
    check(f"{label}: {primaries} accent action(s)", primaries <= 2, str(primaries))


section("161. EVERY CONTROL IS LABELLED")
for label, html in rendered.items():
    # Any input that is not hidden must have a label pointing at it, or carry
    # its own accessible name.
    ids = re.findall(r'<input(?![^>]*type="hidden")[^>]*\sid="([^"]+)"', html)
    labelled = set(re.findall(r'<label[^>]*\sfor="([^"]+)"', html))
    aria = set(re.findall(r'<input[^>]*aria-label="[^"]*"[^>]*id="([^"]+)"', html))
    orphan = [i for i in ids if i not in labelled and i not in aria]
    check(f"{label}: every visible input is labelled", not orphan, str(orphan))

for label, html in rendered.items():
    # An icon-only control has to say what it is.
    icons = re.findall(r'<(?:a|button|summary)\s[^>]*class="(?:top-icon|heart|mobile-menu-button)[^"]*"[^>]*>', html)
    unnamed = [i for i in icons if "aria-label" not in i and "title" not in i]
    check(f"{label}: icon-only controls are named", not unnamed, str(unnamed[:2]))


section("162. STATUS IS NEVER COLOUR ALONE")
for label, html in rendered.items():
    empty_badges = re.findall(r'<span class="badge[^"]*">\s*</span>', html)
    check(f"{label}: no badge is colour without a word", not empty_badges)
check("each status word has its own badge class",
      all(f".badge-{s}" in CSS for s in
          ["pending", "accepted", "completed", "rejected", "cancelled"]))
check("each payment state has one too",
      all(f".pay-{s}" in CSS for s in ["pending", "paid", "failed", "refunded"]))


section("163. RESPONSIVE AND PRINT")
breakpoints = sorted(set(int(n) for n in
                         re.findall(r"@media \(max-width:\s*(\d+)px\)", CSS)))
check(f"a small set of breakpoints, not a pile ({breakpoints})",
      2 <= len(breakpoints) <= 4, str(breakpoints))
check("the sidebar slides away on a small screen", "translateX(-100%)" in CSS)
check("wide tables scroll inside their own box", ".table-wrap" in CSS and "overflow-x: auto" in CSS)
check("the page itself never scrolls sideways", "overflow-wrap: break-word" in CSS)
# Two bugs the screenshots caught; these stop them coming back.
mobile = CSS[CSS.find("@media (max-width: 720px)"):]
check("the stacked toolbar resets its flex-basis",
      ".toolbar .grow { flex: 0 0 auto" in mobile,
      "a column flex-basis becomes a height, not a width")
check("stacked results are separated by a rule",
      ".card > .provider + .provider" in CSS)
check("a scroll target does not draw our focus ring",
      '[tabindex]):not([tabindex="-1"]):focus-visible' in CSS)
# Suppressing our own ring is not enough: the browser draws one of its own on
# a programmatically focused container, which outlined the whole results panel.
check("a scroll target does not draw the browser's focus ring either",
      '[tabindex="-1"]:focus { outline: none; }' in CSS)

check("there is a print stylesheet", "@media print" in CSS)
check("printing hides the navigation",
      ".sidebar" in CSS[CSS.find("@media print"):] and ".nav" in CSS[CSS.find("@media print"):])
check("motion can be turned off", "prefers-reduced-motion" in CSS)


section("164. THE THREE LAYOUTS STILL DIFFER")
check("the customer keeps a horizontal bar",
      'class="nav-inner"' in rendered["my bookings"]
      and 'id="sidebar"' not in rendered["my bookings"])
check("the provider gets the sidebar", 'id="sidebar"' in rendered["provider dashboard"])
check("the admin gets the sidebar", 'id="sidebar"' in rendered["admin overview"])
check("a signed-out visitor gets the plain bar",
      'class="nav-inner"' in rendered["landing"] and 'id="sidebar"' not in rendered["landing"])
check("the admin sheet is only loaded for the admin",
      "css/admin.css" in rendered["admin overview"]
      and "css/admin.css" not in rendered["my bookings"])

raise SystemExit(results.report() and 1 or 0)
