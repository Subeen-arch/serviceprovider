"""MySQL access layer.

One connection is opened per request and closed when the request ends.
Every query goes through these four helpers, and they all use parameterised
SQL (%s placeholders), so user input can never be treated as SQL.
"""

from contextlib import contextmanager

import mysql.connector
from flask import g

import config


class DatabaseError(Exception):
    """Raised when the database cannot be reached or a query fails.

    `connection_failed` separates the two cases, because "MySQL is not running"
    and "that query was wrong" need very different advice.
    """

    def __init__(self, message, connection_failed=False):
        super().__init__(message)
        self.connection_failed = connection_failed


def connect(database=config.DB_NAME):
    """Open a new MySQL connection. Used by the app and by setup_db.py."""
    return mysql.connector.connect(
        host=config.DB_HOST,
        port=config.DB_PORT,
        user=config.DB_USER,
        password=config.DB_PASSWORD,
        database=database,
        autocommit=False,
    )


def get_db():
    """Return the connection for the current request, opening it if needed."""
    if "db" not in g:
        try:
            g.db = connect()
        except mysql.connector.Error as exc:
            raise DatabaseError(
                f"Could not connect to MySQL: {exc}", connection_failed=True
            ) from exc
    return g.db


def close_db(_exception=None):
    """Close the request connection. Registered as a Flask teardown handler."""
    conn = g.pop("db", None)
    if conn is not None:
        conn.close()


def fetch_all(sql, params=()):
    """Run a SELECT and return every row as a list of dictionaries."""
    conn = get_db()
    try:
        with conn.cursor(dictionary=True) as cursor:
            cursor.execute(sql, params)
            return cursor.fetchall()
    except mysql.connector.Error as exc:
        raise DatabaseError(str(exc)) from exc


def fetch_one(sql, params=()):
    """Run a SELECT and return the first row as a dictionary, or None."""
    conn = get_db()
    try:
        with conn.cursor(dictionary=True) as cursor:
            cursor.execute(sql, params)
            return cursor.fetchone()
    except mysql.connector.Error as exc:
        raise DatabaseError(str(exc)) from exc


def execute(sql, params=()):
    """Run an INSERT/UPDATE/DELETE inside a transaction.

    Returns the new row id for an INSERT, otherwise the number of rows changed.
    The transaction is rolled back if the statement fails, so a failed write can
    never leave the database half-updated.
    """
    conn = get_db()
    try:
        with conn.cursor() as cursor:
            cursor.execute(sql, params)
            result = cursor.lastrowid or cursor.rowcount
        conn.commit()
        return result
    except mysql.connector.Error as exc:
        conn.rollback()
        raise DatabaseError(str(exc)) from exc


@contextmanager
def transaction():
    """Provide one connection for a multi-statement atomic operation."""
    conn = get_db()
    try:
        yield conn
        conn.commit()
    except mysql.connector.Error as exc:
        conn.rollback()
        raise DatabaseError(str(exc)) from exc
    except Exception:
        conn.rollback()
        raise
