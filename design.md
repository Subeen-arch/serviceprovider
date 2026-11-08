# Service Expert — Design Brief

A page-by-page brief for redesigning Service Expert in **Claude Design**.

This document describes **what each page is for, what it must contain, and what
the user does there** — never what it currently looks like. Treat every page as
a blank canvas. The only things that are fixed are the content, the data, the
actions and the rules listed here, because the Flask back end already depends
on them.

---

## Contents

1. [The product in one minute](#1-the-product-in-one-minute)
2. [Principles for the best design](#2-principles-for-the-best-design)
3. [Things that appear on every page](#3-things-that-appear-on-every-page)
4. [Public pages](#4-public-pages)
5. [Customer pages](#5-customer-pages)
6. [Provider pages](#6-provider-pages)
7. [Admin pages](#7-admin-pages)
8. [Pages every signed-in role shares](#8-pages-every-signed-in-role-shares)
9. [Journeys to design end to end](#9-journeys-to-design-end-to-end)
10. [States checklist](#10-states-checklist)
11. [Content and formatting rules](#11-content-and-formatting-rules)
12. [Constraints the design must respect](#12-constraints-the-design-must-respect)
13. [How to run this in Claude Design](#13-how-to-run-this-in-claude-design)

---

## 1. The product in one minute

Service Expert helps people in the **Kathmandu valley** find and book a local
service provider — an electrician, plumber, carpenter, cleaner, tutor, gardener
and so on.

A customer picks a service and clicks their location on a map. The system ranks
nearby providers with a **weighted recommendation score** (distance, rating,
price, experience) and calculates the **shortest road route** with Dijkstra's
algorithm. The customer sends a booking request; the provider accepts or
rejects it; once accepted the customer **pays through Khalti**; the provider
does the job and marks it complete; the customer leaves a review.

### Three roles, three very different jobs

| Role | Who they are | What they come to do | How often |
|---|---|---|---|
| **Customer** | A household in Kathmandu | Find someone trustworthy nearby, book, pay, review | Occasionally, often on a phone |
| **Provider** | A tradesperson or small business | Answer requests, manage their jobs, keep their hours and location right | Daily, quick check-ins |
| **Admin** | Whoever runs the platform | Approve providers, watch bookings and money, handle problems | Daily, at a desk, for longer |

Design each role for its own job. A customer screen that looks like an admin
console will feel cold; an admin console that looks like a consumer app will be
slow to work in.

---

## 2. Principles for the best design

### 2.1 Trust first

Hiring a stranger to come into your home is a trust decision. Every screen a
customer sees should answer, at a glance: **who is this, how far away, how much,
how good, and is it confirmed?** Ratings, review counts, experience, distance
and price are the trust signals — give them real visual weight, never bury them
in grey hint text.

### 2.2 Status is the backbone of the whole product

Almost every screen is really about a booking in some state. Design one
**status system** first and reuse it everywhere — badges, tabs, filters, timeline
steps, notification icons.

**Booking status** (5 values)

| Status | Meaning | Who moves it here |
|---|---|---|
| `pending` | Request sent, waiting for the provider | Customer, by booking |
| `accepted` | Provider said yes; customer can now pay | Provider |
| `rejected` | Provider said no; nothing is charged | Provider |
| `completed` | Job done; customer can review | Provider (only once paid) |
| `cancelled` | Customer called it off | Customer |

**Payment status** (4 values, plus "none yet")

| Status | Meaning |
|---|---|
| *not required yet* | No payment exists — normal while a request is pending |
| `pending` | Payment started with Khalti, not confirmed |
| `paid` | Khalti confirmed it |
| `failed` | Cancelled, expired or the amount did not match |
| `refunded` | Money marked for return after a cancel or reject |

Booking status and payment status are **deliberately separate** and a booking
shows both. Design them so they read as two different things side by side, and
never rely on colour alone — pair each with an icon or a word.

### 2.3 One primary action per screen

Each page below lists a **primary action**. Make that the most prominent thing on
the page. Everything else is secondary. On the booking card, the primary action
changes with the status (Pay → Review → Book again), so design the card with a
single action slot that changes, rather than a row of buttons.

### 2.4 Make the algorithms visible

The recommendation score and the Dijkstra route are what make this project more
than a directory. Don't hide them:

- The score (0–100) should be a clear, comparable number on every provider.
- "Why this score?" should open a **breakdown**: four factors, each with its
  weight and the points it earned. Think of it as a receipt for the ranking.
- The route should be drawn on a map with the distance and driving time stated
  plainly, and an optional "how this was calculated" view that lists the
  junctions the shortest path went through.

### 2.5 Density depends on the role

| Role | Density | Think of |
|---|---|---|
| Customer | Spacious, card-based, large tap targets | A booking app |
| Provider | Medium, queue-based — "what needs me now?" | A to-do list |
| Admin | Dense, table-first, fast to scan and filter | A back-office console |

### 2.6 Design every state, not just the happy one

Every list can be empty. Every search can find nothing. Every form can be
rejected. Every map can fail to load. Section 10 lists them — each one needs a
designed state with a clear next step, never a blank space.

### 2.7 Built for Nepal

- Currency is **Rs**, whole rupees in lists, two decimals on money summaries.
- Addresses come back from the map in **English and Devanagari mixed**
  (e.g. *One Durbar Mall, दरबार मार्ग, Kathmandu-1*). Choose typefaces that
  render Devanagari cleanly next to Latin text, and let address lines wrap.
- Phone numbers are 10 digits starting with 9.
- Much of the customer traffic will be on mid-range Android phones — design the
  customer side mobile-first.

### 2.8 Accessible by default

Colour contrast of at least 4.5:1 for text, a visible keyboard focus state,
tap targets of at least 44×44 px, status never shown by colour alone, and every
icon-only button with a text label for screen readers.

---

## 3. Things that appear on every page

### 3.1 Navigation

Each role has its own set of pages. The owner has decided the **customer** gets a
horizontal navigation bar across the top, and the **provider and admin** get a
side navigation — design within that choice.

**Customer navigation**

| Left group (pages) | Right group (icon-only) |
|---|---|
| Find a service · My bookings · Contact · Favourites | Alerts (bell, with unread count) · Account (menu) |

Account menu for a customer: **Manage account**, then **Logout**.

**Provider navigation**

Dashboard · Bookings · Reviews · Hours · My profile · Contact — plus the Alerts
bell and the Account menu in a top bar.

**Admin navigation**

Overview · Providers · Users · Services · Bookings · Payments · Reviews ·
Messages (with an unread count) — plus the Alerts bell and the Account menu in a
top bar.

Account menu for provider and admin: the person's name and email at the top,
then **Profile**, **Security**, a divider, and **Log out**.

**Rules for all navigation**

- Logout appears in exactly one place: inside the Account menu.
- The current page is always highlighted, including on child pages (a single
  booking keeps "Bookings" highlighted).
- On small screens the side navigation collapses behind a menu button.

**Signed-out visitors** see the brand, a Contact link, **Log in** and **Sign up**.

### 3.2 The Alerts bell

Shows a count of unread notifications. Opening the Alerts page marks them read
and the count disappears. Design the count so it is noticeable but not alarming.

### 3.3 Flash messages

After almost every action the next page shows a one-line message: success
("Booking cancelled."), error ("Your current password is not correct.") or
info. Several can appear at once. They must be readable, dismissible or
self-evidently temporary, and must not push the page's primary action out of
view on a phone.

### 3.4 The footer

Brand line and a Contact link. Keep it quiet.

### 3.5 A shared component list

Design these once, as a kit, before any page:

- Buttons: primary, secondary, danger, success, small, full-width, icon-only
- Inputs: text, email, phone, number, date, time, select, textarea, search (with
  icon), password (with a show/hide eye), checkbox, radio, star-rating picker
- Status badges for all 5 booking and 4 payment states
- Cards: provider card, booking card, stat card, empty-state card
- Tables: with a clickable row, a numeric column, a status column, an actions
  column, and horizontal scrolling on small screens
- Filter chips and status tabs with counts
- A drop-down action menu (for table rows)
- A modal dialog (for the cancellation reason)
- A map frame, with loading, error and "no route" variants
- Star display (read-only, 1–5) and a rating distribution bar
- Pagination-ready list footer
- Toast / flash message

---

## 4. Public pages

### 4.1 Landing page — `/`

**Who:** anyone not signed in (signed-in visitors are sent straight to their own
home page).
**Purpose:** explain the product in seconds and get the visitor to sign up.
**Primary action:** Create an account.

**Must contain**

- A headline promise: find a trusted local service provider near you.
- One or two sentences on how it works: choose the help, mark your location,
  compare ranked providers, see the shortest road route.
- **Create an account** and **Log in**.
- **How it works** — five steps: pick a service · mark your location on the map ·
  compare providers by recommendation score · see the shortest route · book and
  review.
- **Services available** — every active service category, each with an emoji
  icon and a name. If none exist, an empty state.

**Design goal:** this is the only marketing page. Make the value obvious, show
the service categories as something inviting to browse, and make the two
differentiators (smart ranking, real road route) feel concrete — a small
illustration of a ranked list or a route on a map would do more than paragraphs.

---

### 4.2 Log in — `/login`

**Primary action:** Log in.

**Must contain**

- Email address and Password (with a show/hide eye).
- **Log in** button.
- "No account yet? Create one" link.
- A separate, quieter link: **Log in as administrator**.

**States:** wrong email or password (one generic message for both — never say
which one was wrong); account deactivated.

---

### 4.3 Administrator login — `/login/admin`

A separate entrance only administrators can use.

**Must contain:** a clear "administrators only" heading and explanation, email,
password, **Log in as administrator**, and a link back to the normal login.
No sign-up link.

**States:** wrong credentials (generic message); a customer or provider using a
correct password here is refused with "This page is for administrators only".

**Design goal:** it should feel noticeably different from the customer login —
more formal, more "staff entrance" — so nobody lands on it by mistake.

---

### 4.4 Sign up — `/register`

**Primary action:** Create account.

**Must contain**

*Your details* — Full name · Email address · Mobile number (98XXXXXXXX) ·
Password · Confirm password.

*I am…* — a choice between **a customer looking for services** and **a provider
offering a service**.

*Your service* (only when "provider" is chosen) —

- Service you provide (list of categories)
- Business or trading name
- Hourly rate (Rs)
- Years of experience
- About your work (optional)
- Where you work from — an address field filled in by **clicking a map**, plus
  the map itself

**Create account** and "I already have an account".

**Rules and states**

- Password: at least 8 characters, mixing letters and numbers.
- Errors per field: name too short, invalid email, phone not 10 digits, weak
  password, passwords don't match, email already registered, provider location
  missing, provider location outside the Kathmandu valley.
- After a provider signs up they are told an administrator must approve them
  before customers can find them.

**Design goal:** the provider half is long. Make the role choice feel like a
fork in the road, reveal the provider section smoothly, and make the map step
unmistakable — it is the step people will miss.

---

### 4.5 Contact — `/contact`

Open to everyone, signed in or not. Messages go to the admin's Messages page.

**Must contain:** Your name · Your email address · Subject (optional, e.g.
"Problem with booking #12") · Your message · **Send message**. A signed-in
person has name and email filled in already.

**States:** message too short; invalid email; success ("Thank you — the
administrator can reply to you at …").

---

### 4.6 Error page

One template for 403, 404, 500 and 503.

**Must contain:** the code, a plain-English sentence, and **Back to the start**.
For 503 (database problem) it may also show a technical detail line for the
developer.

**Design goal:** calm and helpful, never alarming. It must still show the
navigation so the visitor is not stranded.

---

## 5. Customer pages

### 5.1 Find a service — `/search`

The heart of the product. One page that goes from "I need help" to a ranked
list.

**Primary action:** Find providers.

**Step 1 — What do you need?**
A choice of service categories (emoji + name).

**Step 2 — Where are you?**
A map to click on, and an address line that fills itself in from the click
(the customer can edit it). A small "Selected: …" confirmation.

**Optional — Most you want to pay per hour**
A number in Rs, blank means no limit. Note: providers above the budget still
appear, but score 0 for price.

**Recommend by** — five modes, and switching mode re-ranks the same list:

| Mode | Weighting (distance / rating / price / experience) |
|---|---|
| Best overall | 30 / 30 / 25 / 15 |
| Closest | 60 / 20 / 12 / 8 |
| Lowest price | 15 / 17 / 60 / 8 |
| Highest rated | 15 / 60 / 17 / 8 |
| Most experienced | 15 / 20 / 10 / 55 |

**Results** — a heading such as "5 Electricians available", then one card per
provider, best first:

- Business name and the person's name
- **Recommendation score out of 100**
- Road distance in km (from Dijkstra)
- Hourly rate in Rs
- Years of experience
- Average rating and number of reviews, or "No reviews yet"
- Working days summary
- **How this score was calculated** — expands to the four factors, each showing
  its weight, its score and its points, adding up to the total
- **Book** (or view) this provider

**States:** no service chosen; no location chosen; searching (the button shows
progress); no providers near this location; the map failing to load.

**Design goal:** this page must feel effortless on a phone. Keep the three
inputs compact so results appear quickly, make the ranked list the star, and
make the score breakdown genuinely readable — this is the page a viva examiner
will look at hardest.

---

### 5.2 Book a provider — `/book/<provider>`

**Primary action:** Continue to confirmation.

**Left / top — the route**

- **Shortest route** map: the provider's base and the job address as two
  markers, with the road route drawn between them.
- Distance by road and approximate driving time, plus a line saying how many
  points along real roads the route follows.
- **How this provider was ranked (Dijkstra)** — expandable: the junctions the
  shortest path passed through and the distance of each leg.
- States: "Finding the road route…", route unavailable (markers still shown, no
  straight line is ever drawn), and "same location" (no route to travel).

**Right / below — the booking form**

- Header: rate per hour, years of experience, rating and review count.
- Job address (pre-filled from the map, editable).
- **When this provider works** — each working day with its hours
  (e.g. *Monday 06:00 AM – 08:00 PM*).
- Date and Time (06:00–20:00).
- How long will the job take? (1–12 hours).
- What needs doing? (optional note).

**Recent reviews** for this provider, or "No reviews yet".

**Error states the form must show clearly**

- "This provider is not available on Wednesday. They work on: …"
- "This provider works on Monday from 08:00 AM to 05:00 PM."
- "A 2-hour job starting at 07:30 PM would finish at 09:30 PM, but this
  provider stops at 08:00 PM."
- Date in the past; that slot already taken.

**Design goal:** the map and the form compete for attention. Decide which leads
on each screen size. Put the working hours right next to the date and time
inputs — that is where the customer needs them.

---

### 5.3 Confirm your booking — `/book/<provider>/request` (preview)

**Primary action:** Send booking request.

**Must contain**

- Provider business name, service, provider's name.
- When (full date and time), where (address), distance by road, note.
- **Estimated cost**: hourly rate × estimated hours = **Total** in Rs.
- **Payment information** notice: no payment is needed now; the provider
  reviews the request first; if accepted, payment becomes available and must be
  completed before the service goes ahead; if rejected, nothing is charged.
- **Send booking request** and a way back to change details.

**Design goal:** this is a contract moment. It should feel like a clean summary
or ticket — nothing on it the customer needs to wonder about, and the
"you won't be charged yet" message impossible to miss.

---

### 5.4 My bookings — `/bookings`

Every booking this customer has made.

**Primary action:** depends on each booking's status (see the table below).

**Toolbar**

- Search by provider or shop name.
- **Sort by** (8 options): Newest booking first · Oldest booking first ·
  Service date: soonest first · Service date: latest first · Provider name A–Z
  · Provider name Z–A · Shop name A–Z · Status.

A **payment notice** appears at the top while any booking is still pending.

**Each booking card shows**

- Service icon and name · shop name
- Booking status and payment status
- Date and time
- Total in Rs (rate × hours)
- Address, note, and the provider's phone once the job is accepted
- A favourite heart, once a job with this provider has been completed

**Actions by status**

| Booking | Payment | What the customer can do |
|---|---|---|
| pending | not required yet | **Change the date or time** (new date, new time, Move this booking) · Cancel |
| accepted | not paid | **Pay with Khalti** · Cancel |
| accepted | paid | **View receipt** · Cancel (triggers a refund) |
| completed | paid | **Rate this service** (1–5 stars + comment) · View receipt · Favourite |
| completed | reviewed | Their review shown · View receipt |
| rejected / cancelled | — | Nothing; any refund is shown |

**Cancel booking** opens a dialog:

- "Cancel this booking?" and which booking it is (number, service, provider)
- **Why are you cancelling?** — I no longer need this service · I booked the
  wrong date or time · I found another provider · The provider is taking too
  long to respond · The price is higher than I expected · Another reason
- An optional short note for the provider
- **Keep the booking** and **Cancel the booking**

**States:** no bookings yet (with a "Find a service" button); no results for a
search (with "Clear the search"); success messages after paying, cancelling,
rescheduling and reviewing.

**Design goal:** this is the customer's home once they've booked. A card should
tell its whole story in a glance — consider a small progress track
(Requested → Accepted → Paid → Done) so people always know what happens next.

---

### 5.5 Payment receipt — `/bookings/<id>/receipt`

Shown straight after a successful Khalti payment, and any time afterwards.

**Primary action:** Back to my bookings. Secondary: Print this receipt.

**Must contain**

- "Payment receipt" and the booking number
- Paid by (customer name, phone) · Paid to (business, provider, phone)
- Service · Job address · Scheduled date and time
- Paid on · Method (Khalti) · Transaction ID
- Line item: service — hours × rate = amount
- **Total paid**
- "Generated from the payment record confirmed by Khalti."

**Design goal:** it must look like a real receipt and **print cleanly on one A4
page** with the navigation, buttons and messages hidden. A success moment at the
top ("Payment received") when arriving from Khalti will make it feel finished.

---

### 5.6 Favourite providers — `/favourites`

Providers the customer saved. A provider can only be saved after they have
completed a job for this customer.

**Must contain:** a card per provider with business name, service, rate,
experience, rating and review count, a heart to remove them, and a way to book
them again. A provider who is not taking bookings is marked as such.

**Empty state:** "You have not added any favourite service providers yet" with
a link to My bookings.

---

## 6. Provider pages

### 6.1 Dashboard — `/provider/dashboard`

**Primary action:** answer the waiting requests.

**Must contain**

- Business name and a nudge to keep the profile up to date.
- Three figures, each clickable to the filtered booking list: **Waiting for your
  reply** · **Accepted jobs** · **Completed jobs**.
- A short list of recent bookings with the right action on each:
  - pending → **Accept** · **Reject**
  - accepted, unpaid → "Waiting for the customer to pay"
  - accepted, paid → **Mark completed**
  - otherwise → no action needed
- **What customers said** — the latest reviews, or "No reviews yet".

**States:** provider profile missing; awaiting admin approval (they cannot be
found yet); no bookings yet.

**Design goal:** a provider opens this between jobs, often on a phone. Lead with
what needs them right now; everything else is secondary.

---

### 6.2 Bookings — `/provider/bookings`

**Status tabs with counts:** All · Pending · Accepted · Rejected · Completed ·
Cancelled. The counts reflect the current search.

**Search** by customer name — works together with the selected tab.

**Each booking card:** customer name and service icon · booking number · date
and time · booking status and payment status · address · distance · amount for
the hours · the customer's phone once accepted · note · **View details & route
map** · the status-dependent action (Accept / Reject / Mark completed / waiting
for payment) · the customer's rating once reviewed.

**States:** no bookings in this tab; no customer matches the search.

**Design goal:** the tabs are the main navigation of this page. Make each tab's
colour and icon match the status system from section 2.2.

---

### 6.3 One booking — `/provider/bookings/<id>`

**Must contain**

- Booking number, booking and payment status
- **The job**: service, date and time, expected length, address, note, when it
  was requested
- **Customer**: name, and phone "shown once you accept the job"
- **Route to the job** map: from the provider's base to the customer's address,
  with the road distance and the Dijkstra distance used when it was booked
- The status-dependent action
- **What the customer said** (their review, if any)
- Back to my bookings

---

### 6.4 Reviews — `/provider/reviews`

Only this provider's own reviews.

**Must contain**

- **Rating summary**: overall average, star display, total number of reviews,
  and a bar for each of 5★ to 1★ with its count.
- **Filter**: All ratings · 5 Star · 4 Star · 3 Star · 2 Star · 1 Star.
- **Sort**: Newest first · Oldest first · Highest rating · Lowest rating.
- Each review: stars, customer name, service, date, comment.

**States:** no reviews yet; no reviews at the chosen rating ("No 4-star reviews
found", with "Show all ratings").

---

### 6.5 Working hours — `/provider/availability`

**Primary action:** Save working hours.

**Must contain:** each day Monday–Sunday with a **Working** tick-box and a start
and end time. A note that a provider who sets nothing is treated as working
every day 06:00–20:00.

**Errors:** end time before start time, per day.

**Design goal:** it's a weekly schedule. Show it as a week, make "copy these
hours to all weekdays" easy, and make days off obviously off.

---

### 6.6 My profile (business details) — `/provider/profile`

The provider's public-facing details. Separate from their account (name,
phone, password), which lives under the Account menu.

**Must contain**

- Service you provide · Business or trading name · Hourly rate in Rs (with the
  hint that lower rates score better) · Years of experience · About your work
- **I am available for new bookings** — unticking hides them from search
- Approval status: Approved / Awaiting approval
- **Where you work from**: work address and a map to click, with the current
  location shown
- **Save profile**

**Note for the design:** changing the work address, the service or the
availability tick-box notifies the admin. Consider a small hint beside those
fields so providers aren't surprised.

---

## 7. Admin pages

All admin list pages share a pattern: **filter chips**, a **search box**, a
**table**, and a designed "nothing found" state. Design that pattern once.

### 7.1 Overview — `/admin/dashboard`

**Must contain**

- Headline figures, each clickable to the relevant list: Customers · Provider
  accounts · Active services · Total bookings · Reviews submitted · **Waiting
  for approval** · **Money collected** (Rs total from N paid bookings).
- **Bookings by status**: one figure per status, each linking to that filter.
- **Latest bookings**: number, service, customer, provider, when, status — with
  View all.
- **Most booked services**: each with its booking count, linking to that
  service's bookings.

**Design goal:** the admin should be able to tell whether anything needs
attention within five seconds. "Waiting for approval" and any unusual figures
deserve emphasis; the rest is context.

---

### 7.2 Providers — `/admin/providers`

**Filters:** All · Waiting for approval · Approved.
**Search:** business name, owner, email, phone, service, or location. Works
together with the filter.

**Table columns**

| Column | Content |
|---|---|
| Business | Name · 📍 address · **View map** |
| Owner | Name · email · phone |
| Service | Category name |
| Rate | Rs per hour |
| Exp. | Years |
| Rating | Average and review count, or — |
| Status | Approved / Pending · Unavailable · Account off |
| Action | **Approve** or **Deactivate** |

**States:** none waiting for approval; no providers found for a search.

---

### 7.3 Provider location — `/admin/providers/<id>/location`

Opened from **View map**. Shows only that one provider.

**Must contain:** the business name, a map with a single pin on the shop, the
address and coordinates, a details panel (service, owner, email, phone, rate,
experience, number of bookings, approval and availability status, bio), and
**Approve / Deactivate**.

---

### 7.4 Users — `/admin/users`

**Filters:** All roles · Customers · Providers · Admins.
**Search:** name, email or phone.

**Table:** name · email · phone · role · joined · status (active / inactive) ·
**Activate / Deactivate** (with a confirmation). Admin accounts cannot be
deactivated — show that instead of a button.

---

### 7.5 Services — `/admin/services`

**Add a service** form: Service name · Icon (one emoji) · Short description ·
**Add service**.

**All services** table:

| Column | Content |
|---|---|
| Service | Icon and name — **clickable**, opens that service's providers · description |
| Providers | How many providers offer it (also clickable) |
| Status | Visible / Hidden |
| Action | An **Actions** menu: **Update** · **Hide** or **Show** · **Delete** |

**Delete** asks for confirmation, and is refused with an explanation when
providers or bookings still use the service ("…cannot be deleted because 5
providers are assigned to it and 8 bookings use it. Hide it instead…").

---

### 7.6 Edit a service — `/admin/services/<id>/edit`

Name · Icon · Short description · **Save changes** · Cancel. A note that
renaming changes it everywhere, including old bookings, and the current
Visible/Hidden state.

---

### 7.7 A service's providers — `/admin/services/<id>/providers`

Heading "*Service name* providers", the service description, links back to All
services / All providers / Edit this service, then the same provider table as
7.2 without the Service column.

**Empty state:** "No providers found for Gardener."

---

### 7.8 Bookings — `/admin/bookings`

**Filters:** All · Pending · Accepted · Rejected · Completed · Cancelled.
Arriving from "Most booked services" also filters to one service.
**Search:** booking number (`1024`, `#1024` or `BK1024`), customer, provider,
business, service, status or address.

**Table:** # · service · customer · provider · scheduled date and time ·
distance · booking status · payment status and amount · route link. Each row
opens the booking.

---

### 7.9 One booking — `/admin/bookings/<id>`

**Job** — service, scheduled, estimated hours, address, coordinates, distance,
note, requested at.
**People** — customer (name, phone), provider (business, name, phone),
provider base, hourly rate.
**Payment** — amount, status, method, transaction ID, paid at, refunded at — or
"No payment was recorded".
**Review** — stars and comment, or "This booking has not been reviewed".
**Route map** from the provider's base to the job.
Back to all bookings.

---

### 7.10 Payments — `/admin/payments`

**Filters:** by payment status (pending, paid, failed, refunded).
**Table:** booking · customer · provider · service · amount · method ·
transaction ID · payment status · booking status · when.

**Design goal:** money pages must be exact. Right-align amounts, use a
monospaced style for transaction IDs, and make refunded and failed rows
unmistakable.

---

### 7.11 Reviews — `/admin/reviews`

- **Rating summary** for the whole platform (average, total, a bar per star).
- **Filter**: All ratings · 5 Star … 1 Star.
- **Sort**: Newest first · Oldest first · Highest rating · Lowest rating.
- **Table**: booking number (links to the booking) · customer · provider ·
  service · stars · comment · date.

**Empty states:** no reviews yet; no reviews at the chosen rating.

---

### 7.12 Messages — `/admin/messages`

Everything sent through the Contact page.

**Must contain:** two figures (messages received, still unread), a filter for
unread only, and for each message: subject (or "No subject"), sender name and
email, whether they were signed in and as which role, date, the message body,
**Mark read / Mark unread**, and **Delete**. Unread messages come first.

---

## 8. Pages every signed-in role shares

### 8.1 Alerts — `/notifications`

Everything this account has been told, newest first. Opening the page marks
them read.

**Each alert:** New / Seen marker · a **title** (for admin alerts) · the message
· date and time · a View link to the related booking when there is one.

**What each role receives**

| Customer | Provider | Admin |
|---|---|---|
| Request accepted — you can now pay | New booking request | **New Provider Waiting for Approval** |
| Request rejected — not charged | Customer moved a request to a new time | **Provider Location Updated** |
| Job completed — you can review | Customer paid — you can do the job | **Service Availability Updated** |
| | Booking cancelled, with the reason | **Provider Service Changed** |
| | | **Provider Availability Changed** |
| | | **Booking Cancelled** (number, service, provider, customer, reason) |
| | | **Payment Refunded** (amount, customer, booking) |

**Design goal:** give each kind of alert its own icon so a list of them can be
scanned without reading. Admin alerts carry a heading — make the heading the
thing the eye lands on.

**Empty state:** "Nothing to report yet".

---

### 8.2 Account — `/profile`

Reached from the Account menu (Manage account / Profile / Security).

**Details** — Full name · Mobile number · Email (shown but not editable — it is
the login) · **Save changes**.

**Change password** (the Security section) — Current password · New password ·
Confirm new password, each with a show/hide eye · **Change password**. Rules:
at least 8 characters, letters and numbers, different from the current one.

**Providers only:** a link to their business profile (6.6).

---

## 9. Journeys to design end to end

Design these as connected sequences of artboards, not isolated screens. The
gaps between pages are where most products feel clumsy.

**J1 — First booking (customer, on a phone)**
Landing → Sign up → Find a service → choose Electrician → click the map →
ranked results → open a score breakdown → Book → pick date, time, hours →
Confirm → "Request sent" → My bookings (pending).

**J2 — Getting paid (provider and customer)**
Provider gets an alert → Dashboard → Accept → customer gets an alert → My
bookings → **Pay with Khalti** → *(Khalti's own hosted page — not designed
here)* → back to the **Receipt** → provider gets a "paid" alert → Mark completed
→ customer rates the job.

**J3 — Cancelling (customer)**
My bookings → Cancel booking → reason dialog → cancelled card with refund noted
→ the provider and the admin each get an alert.

**J4 — A slot that doesn't fit (customer)**
Book a provider → choose a day they don't work → clear refusal naming the
working days → pick a valid day → Confirm.

**J5 — Approving a provider (admin)**
Alert: new provider → Providers filtered to Waiting for approval → View map to
check the shop's location → Approve → the provider now appears in search.

**J6 — Investigating a problem (admin)**
Message from the Contact page → search Bookings for the booking number →
open the booking → check payment and route → reply by email.

---

## 10. States checklist

Design every one of these. Each needs words and a next step, not just an
illustration.

| Where | State |
|---|---|
| Search | no service chosen · no location · searching · no providers nearby · map failed |
| Provider result | no reviews yet · over budget (price scores 0) · not taking bookings |
| Route map | loading · route found · route unavailable · same location · map not configured |
| Booking form | non-working day · outside hours · job runs past closing · past date · slot taken |
| My bookings | none yet · search found nothing · each status × payment combination in 5.4 |
| Payment | pending with Khalti · paid · failed / cancelled · amount mismatch · refunded |
| Lists (all roles) | empty · filter found nothing · search found nothing |
| Reviews | none yet · none at the chosen rating |
| Alerts | none · unread · read |
| Forms | each field error · success message after saving |
| Accounts | awaiting approval · deactivated · wrong password |
| Anywhere | 403 · 404 · 500 · 503 |

---

## 11. Content and formatting rules

| Thing | Format | Example |
|---|---|---|
| Money in lists | Rs + whole number | Rs 700 |
| Money on summaries and receipts | Rs + two decimals | Rs 1600.00 |
| Booking reference | # + number | #12 |
| Dates in lists | day, short month, year | 05 Sep 2026 |
| Dates in summaries | weekday, day, full month, year | Saturday 05 September 2026 |
| Times | 12-hour in schedules, 24-hour on bookings | 08:00 AM · 14:30 |
| Distance | km, two decimals | 4.32 km |
| Score | out of 100, one decimal | 78.4 / 100 |
| Rating | one decimal and stars | 4.2 ★★★★☆ |
| Duration | hours | 2 hours |
| Phone | 10 digits | 9841000101 |

**Tone:** plain, friendly and specific. Say what happened and what to do next
("Waiting for the customer to pay — you can mark it completed once the payment
arrives"). Never blame the person.

---

## 12. Constraints the design must respect

These come from how the project is built. Designs that ignore them cannot be
implemented without rewriting the back end.

- **Plain HTML, CSS and a little JavaScript**, rendered by Flask/Jinja. No React,
  no component framework, no Bootstrap. Every design must be buildable with
  ordinary CSS (flexbox, grid, custom properties).
- **Every form submits to the server and reloads the page.** Filters, searches
  and sorts live in the URL (`?search=rijal&status=approved`), so a filtered view
  can be bookmarked and survives a refresh. Design filters as things you
  choose, not as live-updating widgets.
- **Menus and dialogs must work without JavaScript** where possible. The row
  action menu and the account menu are native `<details>` elements; the
  cancellation reason is a native `<dialog>`. Their open and closed looks can be
  anything, but the behaviour is fixed.
- **Maps are Galli Maps** embedded in a box. You can design everything around
  the map, the size of the box, the marker colours and the route line colour —
  not the base map tiles themselves.
- **Khalti's checkout is Khalti's own page.** Design the Pay button before it and
  the receipt or failure message after it, not the checkout itself.
- **Icons** must be deliverable as simple inline SVG (a single colour, drawn on a
  24×24 grid). Emoji are used for service categories because admins choose them
  when adding a service.
- **Three layouts, not one:** a public layout, a customer layout with a top bar,
  and a staff layout with side navigation for providers and admins.
- **Must work from 360 px wide phones up to wide desktop monitors.** Wide tables
  scroll sideways inside their own box; the page itself never does.
- **Printable receipt** on one A4 page.

---

## 13. How to run this in Claude Design

### 13.1 Order of work

1. **Design system first** — one artboard with type scale (Latin and
   Devanagari), colour tokens, spacing scale, radii, shadows, and every
   component from section 3.5 in each of its states. Settle the status colours
   and icons here; everything else depends on them.
2. **The customer critical path** — Search, Book, Confirm, My bookings, Receipt.
   Desktop 1440 px and mobile 390 px for each.
3. **The provider day** — Dashboard, Bookings, one booking, Hours.
4. **The admin console** — Overview, Providers, Bookings, one booking, Services.
5. **Everything else** — the remaining pages reuse patterns you will already
   have by this point.
6. **States** — a separate artboard per page for its empty and error states from
   section 10.

### 13.2 Suggested artboards

| # | Artboard | Sizes |
|---|---|---|
| 0 | Design system and components | 1440 |
| 1 | Landing | 1440 · 390 |
| 2 | Log in · Admin log in · Sign up (customer and provider) | 1440 · 390 |
| 3 | Find a service — empty form · ranked results · score breakdown open | 1440 · 390 |
| 4 | Book a provider — route found · refusal message | 1440 · 390 |
| 5 | Confirm booking | 1440 · 390 |
| 6 | My bookings — one card per status · cancel dialog | 1440 · 390 |
| 7 | Receipt — screen and print | 1440 · A4 |
| 8 | Favourites | 1440 · 390 |
| 9 | Provider dashboard | 1440 · 390 |
| 10 | Provider bookings — tabs · one booking with route | 1440 · 390 |
| 11 | Provider reviews · working hours · business profile | 1440 · 390 |
| 12 | Admin overview | 1440 |
| 13 | Admin providers · provider location | 1440 |
| 14 | Admin users · services · edit service · service providers | 1440 |
| 15 | Admin bookings · one booking · payments | 1440 |
| 16 | Admin reviews · messages | 1440 |
| 17 | Alerts (each role) · Account | 1440 · 390 |
| 18 | Error pages | 1440 · 390 |

### 13.3 Prompts that work well

Give Claude Design one page at a time, and paste that page's section from this
document with it. For example:

> Design the **Find a service** page for a local services marketplace in
> Kathmandu. Mobile-first at 390 px, plus a 1440 px desktop version. It needs:
> a service picker, a map the user taps to set their location, an optional
> budget, five recommendation modes, and a ranked list of provider cards. Each
> card shows a recommendation score out of 100, road distance, hourly rate in
> Rs, years of experience, rating and review count, and expands to show how the
> score was calculated from four weighted factors. Use the components from the
> design system artboard. Show the empty state and a no-results state too.

Useful follow-ups:

- "Make the score breakdown easier to understand for someone seeing it for the
  first time."
- "Show this booking card in all six status combinations side by side."
- "This admin table needs to be scanned quickly — increase density and make the
  status column the easiest thing to read."
- "Check every text colour against its background for 4.5:1 contrast."
- "Design how this page looks when printed."

### 13.4 What to hand back for implementation

When a design is settled, export or note down:

- **Tokens** — colours, font families and sizes, spacing, radii and shadows, as
  named values (these become CSS custom properties).
- **Component specs** — padding, borders and each state (default, hover, focus,
  disabled, error) for buttons, inputs, badges, cards and tables.
- **Breakpoints** — the widths where layouts change.
- **Icons** — as SVG files.
- **Page layouts** — which components go where at each breakpoint.

That is everything needed to rebuild the stylesheet and templates around the
existing Flask routes without touching the back end.
