# Service Provider — green UI redesign (v1)

This build keeps the existing Flask/MySQL application and replaces the visual layer with the green/off-white design language supplied in `design.html` and the screenshots.

## What changed

- Shared design system changed to dark green, pale green, off-white and high-contrast status colours.
- Public navigation, customer top navigation, provider/admin sidebar and account menus were restyled.
- Landing page rebuilt around the supplied hero, provider-ranking preview, service grid and process section.
- Added public `/services`, `/how-it-works` and `/for-providers` pages.
- Login and Contact pages were rebuilt in the new style.
- Customer My Bookings, Favourites, Alerts and Account pages were redesigned.
- My Bookings now has status tabs while retaining search, sort, cancel, reschedule, Khalti payment, receipt, review and favourite actions.
- Provider dashboard was rebuilt around requests that need action, current/recent jobs, working hours, reviews and business status.
- Admin overview was rebuilt as a dense back-office dashboard while preserving the real links into users, providers, services, bookings, reviews and payments.
- Existing admin/provider tables and forms inherit the new shared design system without changing their routes or form actions.

## Backend compatibility

The existing authentication, role protection, MySQL schema, Galli Maps integration, recommendation scoring, Dijkstra routing, Khalti flow, password recovery, favourites, reviews, booking status transitions and admin CRUD routes are retained. Only small supporting changes were made for the redesign (public information pages, provider-registration preselection, and customer booking status tabs).

## Running this copy

The downloadable ZIP intentionally does **not** contain `.env`. Put your own local `.env` back in the project root, keep your existing MySQL database, install the requirements in your normal virtual environment, then run:

```bash
python app.py
```

For a completely new database only, run `python setup_db.py` first.

## Validation performed here

- All Python files compile with `py_compile`.
- All Jinja templates parse successfully.
- CSS variables/classes, responsive breakpoints, contrast tokens, inline-style rules and template class references were checked statically.
- Full Flask/MySQL integration tests could not be run in the artifact environment because Flask and mysql-connector are not installed there and outbound package installation is unavailable.
