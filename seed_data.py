"""Sample data so the application can be demonstrated straight away.

Run through setup_db.py. Safe to run more than once: anything that already
exists is skipped rather than duplicated.

Every demo account uses the password from SEED_PASSWORD in the .env file.
"""

from datetime import date, timedelta

import config
from auth import hash_password

SERVICES = [
    ("Electrician",      "⚡", "Wiring, switches, lighting and electrical faults."),
    ("Plumber",          "\U0001f6bf", "Leaks, taps, pipe fitting and bathroom work."),
    ("Carpenter",        "\U0001f528", "Furniture, doors, windows and wood repairs."),
    ("Mechanic",         "\U0001f527", "Two wheeler and car servicing and repairs."),
    ("IT Technician",    "\U0001f4bb", "Computer repair, networking and software setup."),
    ("Cleaner",          "\U0001f9f9", "Home, office and post construction cleaning."),
    ("Tutor",            "\U0001f4da", "Home tuition for school and college subjects."),
    ("Photographer",     "\U0001f4f7", "Events, portraits and product photography."),
    ("Appliance Repair", "\U0001f50c", "Fridge, washing machine, AC and TV repair."),
    ("Painter",          "\U0001f3a8", "Interior and exterior painting and polishing."),
]

# name, email, phone, service, business name, rate, years, address, lat, lng, approved
PROVIDERS = [
    # Electrician
    ("Ramesh Shrestha", "ramesh.s@example.com",  "9841000101", "Electrician", "Shrestha Electric Works", 800,  9, "Thamel, Kathmandu",        27.7154, 85.3123, 1),
    ("Bikash Tamang",   "bikash.t@example.com",  "9841000102", "Electrician", "Bikash Power Solutions",  650,  4, "Koteshwor, Kathmandu",     27.6781, 85.3492, 1),
    ("Sunita Maharjan", "sunita.m@example.com",  "9841000103", "Electrician", "Maharjan Electricals",    950, 14, "Pulchowk, Lalitpur",       27.6790, 85.3172, 1),
    ("Nabin Gurung",    "nabin.g@example.com",   "9841000104", "Electrician", "Gurung Wiring Service",   550,  1, "Balaju, Kathmandu",        27.7356, 85.3022, 1),

    # Plumber
    ("Deepak Karki",    "deepak.k@example.com",  "9841000105", "Plumber",     "Karki Plumbing",          700,  7, "Baneshwor, Kathmandu",     27.6890, 85.3350, 1),
    ("Hari Bahadur",    "hari.b@example.com",    "9841000106", "Plumber",     "Hari Pipe Works",         600, 11, "Kalimati, Kathmandu",      27.6962, 85.2962, 1),
    ("Sabin Thapa",     "sabin.t@example.com",   "9841000107", "Plumber",     "Thapa Sanitary Service",  850,  3, "Chabahil, Kathmandu",      27.7175, 85.3462, 1),

    # Carpenter
    ("Krishna Bhandari","krishna.b@example.com", "9841000108", "Carpenter",   "Bhandari Furniture",      900, 16, "Lagankhel, Lalitpur",      27.6672, 85.3232, 1),
    ("Milan Rai",       "milan.r@example.com",   "9841000109", "Carpenter",   "Rai Wood Craft",          750,  6, "Gongabu, Kathmandu",       27.7356, 85.3122, 1),
    ("Prakash Magar",   "prakash.m@example.com", "9841000110", "Carpenter",   "Magar Doors and Windows", 620,  2, "Kirtipur, Kathmandu",      27.6790, 85.2792, 1),

    # Mechanic
    ("Suresh Adhikari", "suresh.a@example.com",  "9841000111", "Mechanic",    "Adhikari Auto Care",      500,  8, "Kalanki, Kathmandu",       27.6936, 85.2812, 1),
    ("Rajan Basnet",    "rajan.b@example.com",   "9841000112", "Mechanic",    "Basnet Two Wheeler",      450,  5, "Satdobato, Lalitpur",      27.6582, 85.3252, 1),
    ("Anil Chaudhary",  "anil.c@example.com",    "9841000113", "Mechanic",    "Chaudhary Motors",        780, 12, "Tinkune, Kathmandu",       27.6822, 85.3452, 1),

    # IT Technician
    ("Sujan Poudel",    "sujan.p@example.com",   "9841000114", "IT Technician", "Poudel Computer Care",  1000, 6, "Putalisadak, Kathmandu",   27.7052, 85.3222, 1),
    ("Anisha Sharma",   "anisha.s@example.com",  "9841000115", "IT Technician", "Sharma Tech Support",    850, 3, "Jawalakhel, Lalitpur",     27.6732, 85.3122, 1),
    ("Rohit Khadka",    "rohit.k@example.com",   "9841000116", "IT Technician", "Khadka Networks",       1200, 10, "Maharajgunj, Kathmandu",  27.7372, 85.3300, 1),

    # Cleaner
    ("Gita Nepali",     "gita.n@example.com",    "9841000117", "Cleaner",     "Gita Home Cleaning",      400,  5, "Sanepa, Lalitpur",         27.6852, 85.3082, 1),
    ("Maya Lama",       "maya.l@example.com",    "9841000118", "Cleaner",     "Lama Cleaning Service",   500,  9, "Boudha, Kathmandu",        27.7215, 85.3620, 1),
    ("Sarita Bhattarai","sarita.b@example.com",  "9841000119", "Cleaner",     "Sparkle Cleaners",        620,  2, "Baluwatar, Kathmandu",     27.7252, 85.3292, 1),

    # Tutor
    ("Pooja Acharya",   "pooja.a@example.com",   "9841000120", "Tutor",       "Acharya Home Tuition",    600,  4, "Dillibazar, Kathmandu",    27.7062, 85.3292, 1),
    ("Bibek Joshi",     "bibek.j@example.com",   "9841000121", "Tutor",       "Joshi Science Tuition",   900, 11, "Naxal, Kathmandu",         27.7136, 85.3262, 1),
    ("Sneha Dahal",     "sneha.d@example.com",   "9841000122", "Tutor",       "Dahal Maths Classes",     750,  7, "Imadol, Lalitpur",         27.6652, 85.3402, 1),

    # Photographer
    ("Aayush Pradhan",  "aayush.p@example.com",  "9841000123", "Photographer","Pradhan Studio",         1500,  8, "Durbar Marg, Kathmandu",   27.7108, 85.3175, 1),
    ("Nisha Shakya",    "nisha.s@example.com",   "9841000124", "Photographer","Shakya Photography",     1100,  4, "Swayambhu, Kathmandu",     27.7146, 85.2902, 1),

    # Appliance Repair
    ("Manoj Subedi",    "manoj.s@example.com",   "9841000125", "Appliance Repair", "Subedi Appliance Care", 700, 10, "Gaushala, Kathmandu",  27.7085, 85.3440, 1),
    ("Dipesh Rijal",    "dipesh.r@example.com",  "9841000126", "Appliance Repair", "Rijal Cooling Service",  820,  6, "Ekantakuna, Lalitpur", 27.6652, 85.3052, 1),
    ("Kamal Bista",     "kamal.b@example.com",   "9841000127", "Appliance Repair", "Bista Fridge Repair",    560,  3, "Thimi, Bhaktapur",     27.6822, 85.3822, 1),

    # Painter
    ("Ganesh Tandukar", "ganesh.t@example.com",  "9841000128", "Painter",     "Tandukar Painting",       550,  13, "Teku, Kathmandu",         27.6960, 85.3062, 1),
    ("Umesh Giri",      "umesh.g@example.com",   "9841000129", "Painter",     "Giri Colour Works",       680,   5, "Basundhara, Kathmandu",   27.7420, 85.3232, 1),

    # Waiting for admin approval - demonstrates the approval workflow.
    ("Sagar Limbu",     "sagar.l@example.com",   "9841000130", "Electrician", "Limbu Electric Repair",   700,   3, "Jorpati, Kathmandu",      27.7262, 85.3722, 0),
]

CUSTOMERS = [
    ("Aarati Regmi",  "aarati@example.com", "9800000001"),
    ("Nirajan Bhatta", "nirajan@example.com", "9800000002"),
]

ADMIN = ("Site Administrator", "admin@serviceexpert.local", "9800000000")

# Past jobs that produced ratings. (provider email, customer index, rating, comment)
COMPLETED_JOBS = [
    ("ramesh.s@example.com",  0, 5, "Arrived on time and fixed the wiring quickly."),
    ("ramesh.s@example.com",  1, 4, "Good work, slightly expensive."),
    ("sunita.m@example.com",  0, 5, "Very experienced, explained everything clearly."),
    ("sunita.m@example.com",  1, 5, "Excellent service."),
    ("bikash.t@example.com",  0, 3, "Job was done but took longer than promised."),
    ("deepak.k@example.com",  1, 4, "Fixed the leak properly."),
    ("hari.b@example.com",    0, 5, "Honest pricing and neat work."),
    ("krishna.b@example.com", 0, 4, "Nice finishing on the cupboard."),
    ("suresh.a@example.com",  1, 4, "Quick bike servicing."),
    ("sujan.p@example.com",   0, 5, "Recovered my data and cleaned up the laptop."),
    ("gita.n@example.com",    1, 4, "House was spotless."),
    ("bibek.j@example.com",   0, 5, "My daughter's marks improved a lot."),
    ("aayush.p@example.com",  1, 5, "Beautiful photos, worth the price."),
    ("manoj.s@example.com",   0, 3, "Fridge works now but the visit was delayed."),
    ("ganesh.t@example.com",  1, 4, "Clean painting job, no mess left behind."),
]


def _scalar(cursor, sql, params=()):
    cursor.execute(sql, params)
    row = cursor.fetchone()
    return row[0] if row else None


def seed(connection):
    """Insert the sample data. Returns a short summary for the console."""
    cursor = connection.cursor()
    password_hash = hash_password(config.SEED_PASSWORD)
    added = {"services": 0, "users": 0, "providers": 0, "bookings": 0,
             "payments": 0, "reviews": 0}

    # --- services ---
    for name, icon, description in SERVICES:
        cursor.execute("SELECT id FROM services WHERE name = %s", (name,))
        if cursor.fetchone() is None:
            cursor.execute(
                "INSERT INTO services (name, icon, description) VALUES (%s, %s, %s)",
                (name, icon, description),
            )
            added["services"] += 1

    service_ids = {}
    cursor.execute("SELECT id, name FROM services")
    for service_id, name in cursor.fetchall():
        service_ids[name] = service_id

    # --- admin and customers ---
    def ensure_user(name, email, phone, role):
        existing = _scalar(cursor, "SELECT id FROM users WHERE email = %s", (email,))
        if existing:
            return existing
        cursor.execute(
            "INSERT INTO users (name, email, phone, password_hash, role) "
            "VALUES (%s, %s, %s, %s, %s)",
            (name, email, phone, password_hash, role),
        )
        added["users"] += 1
        return cursor.lastrowid

    ensure_user(*ADMIN, "admin")
    customer_ids = [ensure_user(n, e, p, "user") for n, e, p in CUSTOMERS]

    # --- providers ---
    provider_ids = {}
    for (name, email, phone, service, business, rate, years,
         address, lat, lng, approved) in PROVIDERS:
        user_id = ensure_user(name, email, phone, "provider")
        existing = _scalar(
            cursor, "SELECT id FROM providers WHERE user_id = %s", (user_id,)
        )
        if existing:
            provider_ids[email] = existing
            continue
        cursor.execute(
            "INSERT INTO providers (user_id, service_id, business_name, bio, "
            "hourly_rate, experience_years, address, latitude, longitude, "
            "is_available, is_approved) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 1, %s)",
            (
                user_id, service_ids[service], business,
                f"{business} has been serving the Kathmandu valley for "
                f"{years} year{'s' if years != 1 else ''}.",
                rate, years, address, lat, lng, approved,
            ),
        )
        provider_ids[email] = cursor.lastrowid
        added["providers"] += 1

    # --- completed jobs with reviews ---
    for offset, (email, customer_index, rating, comment) in enumerate(COMPLETED_JOBS):
        provider_id = provider_ids[email]
        user_id = customer_ids[customer_index]
        job_date = date.today() - timedelta(days=offset + 3)

        cursor.execute("SELECT service_id, address, latitude, longitude, hourly_rate "
                       "FROM providers WHERE id = %s", (provider_id,))
        service_id, address, lat, lng, hourly_rate = cursor.fetchone()
        hours = 2

        # Each of the three rows is checked on its own, so a database seeded by
        # an older version of this file still gets the parts it is missing.
        # Identified by a fixed marker, NOT by the date. job_date is worked out
        # from today, so on any later day the dates would no longer match and
        # the whole sample set would be inserted a second time.
        marker = f"Sample job {offset + 1}"
        booking_id = _scalar(
            cursor,
            "SELECT id FROM bookings WHERE user_id = %s AND provider_id = %s "
            "AND note = %s",
            (user_id, provider_id, marker),
        )
        if booking_id is None:
            cursor.execute(
                "INSERT INTO bookings (user_id, provider_id, service_id, scheduled_date, "
                "scheduled_time, address, latitude, longitude, note, estimated_hours, "
                "distance_km, status) "
                "VALUES (%s, %s, %s, %s, '10:00:00', %s, %s, %s, %s, %s, NULL, 'completed')",
                (user_id, provider_id, service_id, job_date, address, lat, lng,
                 marker, hours),
            )
            booking_id = cursor.lastrowid
            added["bookings"] += 1

        # These are past jobs invented for the demo, so the payment is marked
        # 'sample' rather than 'khalti' - no real Khalti transaction exists and
        # none is invented.
        if _scalar(cursor, "SELECT id FROM payments WHERE booking_id = %s",
                   (booking_id,)) is None:
            cursor.execute(
                "INSERT INTO payments (booking_id, user_id, amount, payment_method, "
                "status, paid_at) VALUES (%s, %s, %s, 'sample', 'paid', %s)",
                (booking_id, user_id, hourly_rate * hours, job_date),
            )
            added["payments"] += 1

        if _scalar(cursor, "SELECT id FROM reviews WHERE booking_id = %s",
                   (booking_id,)) is None:
            cursor.execute(
                "INSERT INTO reviews (booking_id, user_id, provider_id, rating, comment) "
                "VALUES (%s, %s, %s, %s, %s)",
                (booking_id, user_id, provider_id, rating, comment),
            )
            added["reviews"] += 1

    connection.commit()
    cursor.close()
    return added
