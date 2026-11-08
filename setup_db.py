"""Create the database, build the tables and load the sample data.

Run once before starting the app:

    python setup_db.py

It can be run again safely - the tables use CREATE TABLE IF NOT EXISTS and the
sample data skips anything that is already there.
"""

import sys
from pathlib import Path

import mysql.connector

import config
import db
import seed_data

SCHEMA_FILE = Path(__file__).parent / "schema.sql"


def split_statements(sql_text):
    """Split schema.sql into individual statements, ignoring comment lines."""
    lines = [
        line for line in sql_text.splitlines()
        if not line.strip().startswith("--")
    ]
    return [s.strip() for s in "\n".join(lines).split(";") if s.strip()]


# Columns added after the first version of the schema. CREATE TABLE IF NOT
# EXISTS leaves an existing table alone, so a database built before these
# columns existed needs them added here.
LATER_COLUMNS = [
    # Incremented whenever a password changes, invalidating every session that
    # was signed before that change.
    ("users", "auth_version",
     "ALTER TABLE users ADD COLUMN auth_version INT NOT NULL DEFAULT 0 "
     "AFTER password_hash"),
    ("bookings", "estimated_hours",
     "ALTER TABLE bookings ADD COLUMN estimated_hours TINYINT NOT NULL DEFAULT 1 "
     "AFTER note"),
    # A heading for a notification, e.g. "Provider Location Updated". Older
    # rows keep '' and still read correctly as a plain sentence.
    ("notifications", "title",
     "ALTER TABLE notifications ADD COLUMN title VARCHAR(120) NOT NULL DEFAULT '' "
     "AFTER booking_id"),
    # Why the customer cancelled, chosen in the box that appears when they
    # press Cancel. Empty for bookings that were never cancelled.
    ("bookings", "cancel_reason",
     "ALTER TABLE bookings ADD COLUMN cancel_reason VARCHAR(200) NOT NULL DEFAULT '' "
     "AFTER status"),
]


def add_missing_columns(cursor, connection):
    """Bring an older database up to date without touching its data."""
    added = 0
    for table, column, statement in LATER_COLUMNS:
        cursor.execute(
            "SELECT COUNT(*) FROM information_schema.COLUMNS "
            "WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s AND COLUMN_NAME = %s",
            (config.DB_NAME, table, column),
        )
        if cursor.fetchone()[0] == 0:
            cursor.execute(statement)
            added += 1
            print(f"Added missing column {table}.{column}.")
    if added:
        connection.commit()


def add_double_booking_lock(cursor, connection):
    """Let the database itself refuse two live bookings in the same slot.

    `active_slot` is generated: it holds "provider|date|time" while a booking is
    pending or accepted, and NULL once it is rejected, cancelled or completed.
    MySQL permits any number of NULLs in a UNIQUE index, so a freed slot can be
    booked again while a live one cannot be taken twice.

    The column is VIRTUAL rather than STORED: a stored column would force
    MySQL to rebuild the whole bookings table, which fails because payments,
    reviews and notifications all point at it with foreign keys.

    Both statements are skipped when they have already been applied, so setup
    can be run as often as you like. The same SQL is written out in schema.sql
    for anyone applying it by hand in Workbench.
    """
    changed = False

    cursor.execute(
        "SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = %s "
        "AND TABLE_NAME = 'bookings' AND COLUMN_NAME = 'active_slot'",
        (config.DB_NAME,),
    )
    if cursor.fetchone()[0] == 0:
        cursor.execute(
            "ALTER TABLE bookings ADD COLUMN active_slot VARCHAR(64) "
            "GENERATED ALWAYS AS ("
            "  CASE WHEN status IN ('pending', 'accepted') "
            "       THEN CONCAT(provider_id, '|', scheduled_date, '|', scheduled_time) "
            "  END"
            ") VIRTUAL"
        )
        print("Added generated column bookings.active_slot.")
        changed = True

    cursor.execute(
        "SELECT COUNT(*) FROM information_schema.STATISTICS WHERE TABLE_SCHEMA = %s "
        "AND TABLE_NAME = 'bookings' AND INDEX_NAME = 'uq_bookings_active_slot'",
        (config.DB_NAME,),
    )
    if cursor.fetchone()[0] == 0:
        try:
            cursor.execute(
                "ALTER TABLE bookings "
                "ADD CONSTRAINT uq_bookings_active_slot UNIQUE (active_slot)"
            )
            print("Added unique index uq_bookings_active_slot.")
            changed = True
        except mysql.connector.Error as exc:
            # Existing data already holds the same slot twice. Say so plainly
            # rather than failing the whole setup.
            print(f"\nCould not add the double-booking lock: {exc}")
            print("Two live bookings already share a provider, date and time. "
                  "Cancel one of them and run setup again.")

    if changed:
        connection.commit()


def main():
    print(f"Connecting to MySQL at {config.DB_HOST}:{config.DB_PORT} "
          f"as '{config.DB_USER}' ...")

    try:
        # Connect with no database selected so it can be created.
        server = mysql.connector.connect(
            host=config.DB_HOST,
            port=config.DB_PORT,
            user=config.DB_USER,
            password=config.DB_PASSWORD,
        )
    except mysql.connector.Error as exc:
        print(f"\nCould not connect to MySQL: {exc}")
        print("Check that MySQL is running and that DB_USER / DB_PASSWORD "
              "in your .env file are correct.")
        return 1

    cursor = server.cursor()
    cursor.execute(
        f"CREATE DATABASE IF NOT EXISTS `{config.DB_NAME}` "
        "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
    )
    cursor.close()
    server.close()
    print(f"Database '{config.DB_NAME}' is ready.")

    connection = db.connect()
    cursor = connection.cursor()

    statements = split_statements(SCHEMA_FILE.read_text(encoding="utf-8"))
    for statement in statements:
        cursor.execute(statement)
    connection.commit()
    print(f"Tables created ({len(statements)} statements).")

    add_missing_columns(cursor, connection)
    add_double_booking_lock(cursor, connection)
    cursor.close()

    added = seed_data.seed(connection)
    connection.close()

    print(
        "Sample data loaded: "
        + ", ".join(f"{count} {name}" for name, count in added.items())
    )
    print("\nDemo accounts (password: " + config.SEED_PASSWORD + ")")
    print("  admin     " + seed_data.ADMIN[1])
    print("  customer  " + seed_data.CUSTOMERS[0][1])
    print("  provider  " + seed_data.PROVIDERS[0][1])
    print("\nNow run:  python app.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
