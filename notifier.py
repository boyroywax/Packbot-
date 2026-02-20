"""Email notification helpers for Packbot.

Configure via environment variables (all optional – notifications are disabled
when SMTP_HOST is not set):

    SMTP_HOST      – e.g. smtp.gmail.com
    SMTP_PORT      – default 587 (STARTTLS); use 465 for SSL
    SMTP_USER      – login username
    SMTP_PASSWORD  – login password
    SMTP_FROM      – From: address (defaults to SMTP_USER)
    APP_BASE_URL   – used to build links in email bodies
"""

import os
import smtplib
import threading
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText


def _smtp_enabled() -> bool:
    return bool(os.getenv("SMTP_HOST"))


def send_email(to: str, subject: str, body_html: str, body_text: str = "") -> None:
    """Fire-and-forget email send.  No-ops silently if SMTP is not configured."""
    if not _smtp_enabled() or not to:
        return
    threading.Thread(
        target=_send_blocking,
        args=(to, subject, body_html, body_text or _html_to_plain(body_html)),
        daemon=True,
    ).start()


def _html_to_plain(html: str) -> str:
    """Crude HTML → plain-text strip for the text/plain MIME part."""
    import re
    return re.sub(r"<[^>]+>", "", html).strip()


def _send_blocking(to: str, subject: str, body_html: str, body_text: str) -> None:
    """Blocking SMTP send – runs inside a daemon thread."""
    host      = os.getenv("SMTP_HOST", "")
    port      = int(os.getenv("SMTP_PORT", 587))
    user      = os.getenv("SMTP_USER", "")
    password  = os.getenv("SMTP_PASSWORD", "")
    from_addr = os.getenv("SMTP_FROM", user)

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = from_addr
    msg["To"]      = to
    msg.attach(MIMEText(body_text, "plain"))
    msg.attach(MIMEText(body_html, "html"))

    try:
        with smtplib.SMTP(host, port, timeout=10) as smtp:
            smtp.ehlo()
            smtp.starttls()
            if user and password:
                smtp.login(user, password)
            smtp.sendmail(from_addr, [to], msg.as_string())
    except Exception:
        pass  # notifications are best-effort


# ---------------------------------------------------------------------------
# Typed notification helpers
# ---------------------------------------------------------------------------

def notify_new_message(
    recipient_email: str,
    sender_username: str,
    subject: str,
) -> None:
    """Notify *recipient_email* that *sender_username* sent them a message."""
    if not recipient_email:
        return
    base = os.getenv("APP_BASE_URL", "").rstrip("/")
    link = f'<a href="{base}">View it on Packbot</a>' if base else "Open Packbot to view it."
    html = f"""
    <p>Hi,</p>
    <p><strong>{sender_username}</strong> sent you a message on Packbot:</p>
    <blockquote style="color:#555;border-left:3px solid #f6c90e;padding-left:10px">
      <em>{subject or '(no subject)'}</em>
    </blockquote>
    <p>{link}</p>
    <p style="color:#999;font-size:12px">
      You received this because you have an email address on your Packbot account.
    </p>
    """
    send_email(
        to=recipient_email,
        subject=f"Packbot: New message from {sender_username}",
        body_html=html,
    )


def notify_trade_match(
    user_email: str,
    matcher_username: str,
    card_name: str,
) -> None:
    """Notify *user_email* that a new trade match was found for *card_name*."""
    if not user_email:
        return
    base = os.getenv("APP_BASE_URL", "").rstrip("/")
    link = f'<a href="{base}">View Trade Matches on Packbot</a>' if base else "Open Packbot to view matches."
    html = f"""
    <p>Hi,</p>
    <p>A new trade match was found for <strong>{card_name}</strong>:</p>
    <p><strong>{matcher_username}</strong> has this card listed for trade.</p>
    <p>{link}</p>
    <p style="color:#999;font-size:12px">
      You received this because the card is on your Packbot wishlist.
    </p>
    """
    send_email(
        to=user_email,
        subject=f"Packbot: Trade match found for {card_name}",
        body_html=html,
    )
