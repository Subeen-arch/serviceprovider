"""Shared plumbing for the test suites.

Two jobs:

1. Point the application at a **separate** test database before it is imported,
   so a test run can never touch the real `service_expert` data. The name is
   whatever DB_NAME is in .env with `_test` on the end.

2. Give every suite the same small set of helpers - connect, query, execute,
   log in, and record a pass or a fail - so the suites themselves only contain
   the checks they are actually about.
"""

import os
import sys

# Make the project importable no matter which folder the tests are run from.
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# Every request in a test goes through Flask's test client, which needs a host
# name for the session cookie to stick between calls.
BASE = "http://127.0.0.1:5000"

SEED_PASSWORD = os.environ.get("SEED_PASSWORD", "Demo@1234")

ADMIN_EMAIL = "admin@serviceexpert.local"
CUSTOMER_EMAIL = "aarati@example.com"
PROVIDER_EMAIL = "ramesh.s@example.com"


def use_test_database():
    """Switch DB_NAME to the test copy. Must run before `import app`.

    Everything else - host, port, user, password - is left exactly as it is in
    .env, so the tests use the same MySQL server the application does. Only the
    database name changes.
    """
    if os.environ.get("SERVICE_EXPERT_TEST_DB"):
        # Already set by run_all.py, or overridden by hand.
        os.environ["DB_NAME"] = os.environ["SERVICE_EXPERT_TEST_DB"]
        return os.environ["DB_NAME"]

    # config reads .env, so importing it here fills in whatever is not already
    # in the environment.
    import config

    name = os.environ.get("DB_NAME", config.DB_NAME)
    if not name.endswith("_test"):
        name += "_test"
    os.environ["DB_NAME"] = name
    os.environ["SERVICE_EXPERT_TEST_DB"] = name
    return name


def real_database_name():
    """The database the application itself uses, straight from .env.

    Read before use_test_database() changes anything, so run_all.py can refuse
    to drop the database the project actually runs on.
    """
    import config
    return config.DB_NAME


def settings():
    """The MySQL connection settings the tests should use."""
    import config
    return {
        "host": os.environ.get("DB_HOST", config.DB_HOST),
        "port": int(os.environ.get("DB_PORT", config.DB_PORT)),
        "user": os.environ.get("DB_USER", config.DB_USER),
        "password": os.environ.get("DB_PASSWORD", config.DB_PASSWORD),
    }


def connect(database=None):
    """A direct MySQL connection, used to check what the app really wrote."""
    import mysql.connector
    options = settings()
    options["database"] = database or os.environ["DB_NAME"]
    return mysql.connector.connect(**options)


def connect_server():
    """A connection to the MySQL server itself, with no database selected.

    Needed to create and drop the test database, which cannot be done from
    inside the database being dropped.
    """
    import mysql.connector
    return mysql.connector.connect(**settings())


def q(sql, params=()):
    """Run a SELECT and return the rows as dictionaries."""
    connection = connect()
    cursor = connection.cursor(dictionary=True)
    cursor.execute(sql, params)
    rows = cursor.fetchall()
    cursor.close()
    connection.close()
    return rows


def ex(sql, params=()):
    """Run an INSERT / UPDATE / DELETE and commit it."""
    connection = connect()
    cursor = connection.cursor()
    cursor.execute(sql, params)
    connection.commit()
    cursor.close()
    connection.close()


def client(email=None, password=None):
    """A Flask test client, logged in as `email` when one is given."""
    from app import app
    test_client = app.test_client()
    if email:
        test_client.post(
            "/login",
            data={"email": email, "password": password or SEED_PASSWORD},
            base_url=BASE,
        )
    return test_client


def body(response):
    """The response HTML with runs of whitespace collapsed.

    Templates wrap lines wherever they like, so collapsing whitespace is what
    lets a test look for a phrase without caring how it was laid out.
    """
    return " ".join(response.get_data(as_text=True).split())


class Results:
    """Counts the checks in one suite and prints them as they run."""

    def __init__(self, title):
        self.title = title
        self.passed = []
        self.failed = []

    def check(self, name, condition, detail=""):
        (self.passed if condition else self.failed).append(name)
        mark = "  PASS  " if condition else "  FAIL  "
        note = f"   [{detail}]" if detail and not condition else ""
        print(mark + name + note)
        return bool(condition)

    def section(self, title):
        print("\n########## " + title + " ##########")

    def report(self):
        """Print the summary and return the number of failures."""
        print(f"\n===== {self.title}: {len(self.passed)} passed, "
              f"{len(self.failed)} failed =====")
        if self.failed:
            print("FAILURES:")
            for name in self.failed:
                print("   -", name)
        return len(self.failed)
