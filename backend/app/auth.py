from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import smtplib
import ssl
from datetime import datetime, timezone
from email.message import EmailMessage


PASSWORD_ITERATIONS = 260_000


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def normalize_email(email: str) -> str:
    return email.strip().lower()


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PASSWORD_ITERATIONS)
    return "pbkdf2_sha256${}${}${}".format(
        PASSWORD_ITERATIONS,
        base64.b64encode(salt).decode("ascii"),
        base64.b64encode(digest).decode("ascii"),
    )


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        scheme, iterations_raw, salt_raw, digest_raw = stored_hash.split("$", 3)
        if scheme != "pbkdf2_sha256":
            return False
        iterations = int(iterations_raw)
        salt = base64.b64decode(salt_raw.encode("ascii"))
        expected = base64.b64decode(digest_raw.encode("ascii"))
    except (ValueError, TypeError):
        return False

    actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return hmac.compare_digest(actual, expected)


def new_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def send_reset_email(
    *,
    to_email: str,
    reset_link: str,
    smtp_host: str,
    smtp_port: int,
    smtp_username: str,
    smtp_password: str,
    smtp_from: str,
    use_tls: bool,
) -> None:
    message = EmailMessage()
    message["Subject"] = "Reset your Variant Research Workbench password"
    message["From"] = smtp_from
    message["To"] = to_email
    message.set_content(
        "\n".join(
            [
                "You requested a password reset for Variant Research Workbench.",
                "",
                f"Reset your password here: {reset_link}",
                "",
                "This link expires soon. If you did not request this, you can ignore this email.",
            ]
        )
    )

    if use_tls:
        context = ssl.create_default_context()
        with smtplib.SMTP_SSL(smtp_host, smtp_port, context=context) as server:
            if smtp_username:
                server.login(smtp_username, smtp_password)
            server.send_message(message)
        return

    with smtplib.SMTP(smtp_host, smtp_port) as server:
        server.starttls(context=ssl.create_default_context())
        if smtp_username:
            server.login(smtp_username, smtp_password)
        server.send_message(message)

