"""Form input checks shared by the customer and provider routes.

Anything that arrives from a browser is converted here and rejected if it is not
what it claims to be, so routes can assume they are working with real values.
"""

import re
from datetime import date, datetime, time

import config

PHONE_PATTERN = re.compile(r"^9\d{9}$")
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[a-zA-Z]{2,}$")


class ValidationError(Exception):
    """Raised when submitted data is not usable. The message is shown to the user."""


def parse_coordinates(raw_lat, raw_lng):
    """Turn the latitude/longitude posted by the map into two floats.

    The routing graph only covers the Kathmandu valley, so a location outside
    it is refused instead of producing a route that would be meaningless.
    """
    try:
        lat = float(raw_lat)
        lng = float(raw_lng)
    except (TypeError, ValueError):
        raise ValidationError("Please select a location on the map first.")

    bounds = config.VALLEY_BOUNDS
    if not (bounds["min_lat"] <= lat <= bounds["max_lat"]):
        raise ValidationError("That location is outside the Kathmandu valley.")
    if not (bounds["min_lng"] <= lng <= bounds["max_lng"]):
        raise ValidationError("That location is outside the Kathmandu valley.")

    return lat, lng


def parse_schedule(raw_date, raw_time):
    """Validate the requested date and time for a booking."""
    try:
        booking_date = datetime.strptime(raw_date or "", "%Y-%m-%d").date()
    except ValueError:
        raise ValidationError("Please choose a valid date.")

    try:
        booking_time = datetime.strptime(raw_time or "", "%H:%M").time()
    except ValueError:
        raise ValidationError("Please choose a valid time.")

    if booking_date < date.today():
        raise ValidationError("The date cannot be in the past.")

    if booking_date == date.today() and booking_time <= datetime.now().time():
        raise ValidationError("That time has already passed today.")

    if not (time(6, 0) <= booking_time <= time(20, 0)):
        raise ValidationError("Bookings are only available between 06:00 and 20:00.")

    return booking_date, booking_time


def parse_positive_number(raw, field, maximum):
    try:
        value = float(raw)
    except (TypeError, ValueError):
        raise ValidationError(f"{field} must be a number.")
    if value < 0 or value > maximum:
        raise ValidationError(f"{field} must be between 0 and {maximum:g}.")
    return value


def parse_rating(raw):
    try:
        rating = int(raw)
    except (TypeError, ValueError):
        raise ValidationError("Please choose a rating.")
    if not 1 <= rating <= 5:
        raise ValidationError("Rating must be between 1 and 5 stars.")
    return rating


def clean_text(raw, field, max_length, required=True, min_length=1):
    value = (raw or "").strip()
    if required:
        # An empty box and a too-short answer are different mistakes, so they
        # get different messages instead of both saying "is required".
        if not value:
            raise ValidationError(f"{field} is required.")
        if len(value) < min_length:
            raise ValidationError(
                f"{field} must be at least {min_length} characters long."
            )
    if len(value) > max_length:
        raise ValidationError(f"{field} cannot be longer than {max_length} characters.")
    return value


def parse_phone(raw):
    """Nepali mobile number: 10 digits starting with 9."""
    value = (raw or "").strip()
    if not PHONE_PATTERN.match(value):
        raise ValidationError("Phone must be 10 digits and start with 9.")
    return value

def parse_clock(raw, field="Time"):
    """Read an HH:MM value from a form and return a datetime.time."""
    try:
        return datetime.strptime((raw or "").strip(), "%H:%M").time()
    except ValueError:
        raise ValidationError(f"{field} must be a time like 09:00.")


def as_clock(value):
    """Show a stored TIME as HH:MM.

    MySQL returns a TIME column as a timedelta, so it has to be converted
    rather than formatted directly.
    """
    if value is None:
        return ""
    if hasattr(value, "total_seconds"):
        minutes = int(value.total_seconds()) // 60
        return f"{minutes // 60:02d}:{minutes % 60:02d}"
    return value.strftime("%H:%M")


def parse_email(raw, field="Email address"):
    """Read an email address from a form, lower-cased."""
    value = (raw or "").strip().lower()
    if not EMAIL_PATTERN.match(value):
        raise ValidationError(f"Please enter a valid {field.lower()}.")
    if len(value) > 120:
        raise ValidationError(f"{field} is too long.")
    return value
