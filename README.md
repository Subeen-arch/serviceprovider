# Service Expert

Find and book local service providers in the Kathmandu valley.

## Setup

1. **Install the dependencies**

   ```
   pip install -r requirements.txt
   ```

2. **Create your settings file**

   ```
   copy .env.example .env
   ```

   Then open `.env` and set at least:

   - `SECRET_KEY` — generate one with
     `python -c "import secrets; print(secrets.token_hex(32))"`
   - `DB_PASSWORD` — your MySQL root password (leave blank if there is none)
   - `GALLI_ACCESS_TOKEN` — your token from <https://gallimaps.com>
   - `KHALTI_SECRET_KEY` — from <https://test-admin.khalti.com> (see below)

   Password recovery also needs `RESET_BASE_URL` and the `MAIL_*` SMTP values
   from `.env.example`. In production, use an HTTPS URL and set
   `SESSION_COOKIE_SECURE=true`.

3. **Create the database and load the sample data**

   ```
   python setup_db.py
   ```

   Safe to run again; it skips anything that already exists.

4. **Start the application**

   ```
   python app.py
   ```

   Open <http://127.0.0.1:5000>.

## Running the tests

```
python tests/run_all.py
```

This creates a separate database called `service_expert_test`, loads the sample
data into it, runs all seventeen suites and drops it again. Your own
`service_expert` database is never opened, so a test run cannot change your
bookings, providers or payments. The runner refuses to start if those two names
would ever come out the same.

```
python tests/run_all.py 07 11     only those suites
python tests/run_all.py --keep    leave the test database in place to look at
python tests/test_07_recommendation.py    one suite on its own
```

Some checks in `test_03` and `test_05` call Galli APIs, and `test_04` talks to
the Khalti sandbox, so those checks need an internet connection.

## Demo accounts

All use the password in `SEED_PASSWORD` (`Demo@1234` by default).

| Role     | Email                       |
| -------- | --------------------------- |
| Admin    | `admin@serviceexpert.local` |
| Customer | `aarati@example.com`        |
| Provider | `ramesh.s@example.com`      |

## Paying with Khalti (sandbox)

Booking and paying are one flow: pick a provider, fill in the details, check the
confirmation page, then pay. The booking is created with status `pending` and
its payment with status `pending`; the payment only becomes `paid` after the
Flask server asks Khalti's lookup API what really happened.

Booking status and payment status are deliberately separate, so a booking can be
`pending` (waiting for the provider) while its payment is already `paid`.

To test a payment, log in on Khalti's page with:

| Field | Value |
| ----- | ----- |
| Khalti ID | `9800000000` … `9800000005` |
| MPIN | `1111` |
| OTP | `987654` |

Two things worth knowing:

- The query string Khalti adds to the return URL (including `status=Completed`)
  is never trusted, because anyone could type that URL. Only the answer from the
  lookup API can mark a payment paid, and the amount is checked too.
- `KHALTI_SECRET_KEY` is used only in server-to-server requests. It is never
  passed to a template, so it cannot appear in HTML or JavaScript.

Khalti's older checkout widget (the one that takes a public key in the browser)
is not used — this is the current ePayment API v2.

## Layout

```
app.py              Flask app, error handlers, template helpers
config.py           settings, all read from .env
db.py               MySQL connection + parameterised query helpers
auth.py             password hashing, sessions, role decorators
validators.py       form input checks
queries.py          the SQL that more than one route needs
khalti.py           Khalti ePayment API v2 client (initiate + lookup)
schema.sql          table definitions
setup_db.py         creates the database, runs schema.sql, seeds
seed_data.py        sample services, providers, bookings and reviews
algorithms/
  road_graph.py     Kathmandu junctions and the roads between them
  dijkstra.py       shortest path, written out by hand
  recommendation.py weighted provider scoring
routes/             one blueprint per role
templates/          Jinja templates, one folder per role
static/             shared CSS, admin CSS, Galli Maps integration
tests/              one suite per area, plus run_all.py
```

## Password reset email

The login page links to a password-recovery form. Reset links expire after
`RESET_TOKEN_TTL_MINUTES` (30 by default), can be used once, and are built from
`RESET_BASE_URL`. Configure the `MAIL_*` values in `.env` for your SMTP
provider. Port 587 with `MAIL_USE_TLS=true` is the usual STARTTLS setup; port
465 with `MAIL_USE_SSL=true` uses implicit TLS. Do not enable both modes.
