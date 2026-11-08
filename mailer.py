"""SMTP delivery for account email, using only the Python standard library."""

from email.message import EmailMessage
import smtplib
import ssl

import config


class MailDeliveryError(Exception):
    """Raised when mail is unconfigured or the SMTP server rejects delivery."""


def is_configured():
    """True when .env names a real mail server, not the .env.example sample."""
    placeholders = ("example.com", "your-smtp")
    values = (config.MAIL_SERVER, config.MAIL_FROM)
    return all(values) and not any(p in v for v in values for p in placeholders)


def send_password_reset_email(recipient, name, reset_url):
    if not config.MAIL_SERVER or not config.MAIL_FROM:
        raise MailDeliveryError(
            "MAIL_SERVER and MAIL_FROM must be configured in .env"
        )
    if config.MAIL_USE_TLS and config.MAIL_USE_SSL:
        raise MailDeliveryError("MAIL_USE_TLS and MAIL_USE_SSL cannot both be true")

    message = EmailMessage()
    message["Subject"] = "Reset your Service Provider password"
    message["From"] = config.MAIL_FROM
    message["To"] = recipient
    message.set_content(
        f"Hello {name},\n\n"
        "We received a request to reset your Service Provider password. "
        f"Use this link within {config.RESET_TOKEN_TTL_MINUTES} minutes:\n\n"
        f"{reset_url}\n\n"
        "If you did not request this, you can ignore this email. Your password "
        "has not been changed.\n"
    )

    try:
        if config.MAIL_USE_SSL:
            server = smtplib.SMTP_SSL(
                config.MAIL_SERVER, config.MAIL_PORT,
                context=ssl.create_default_context(), timeout=15,
            )
        else:
            server = smtplib.SMTP(config.MAIL_SERVER, config.MAIL_PORT, timeout=15)
        with server:
            if config.MAIL_USE_TLS:
                server.starttls(context=ssl.create_default_context())
            if config.MAIL_USERNAME:
                server.login(config.MAIL_USERNAME, config.MAIL_PASSWORD)
            server.send_message(message)
    except (OSError, smtplib.SMTPException) as exc:
        raise MailDeliveryError(str(exc)) from exc
