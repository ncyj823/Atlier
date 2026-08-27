"""
app/services/email_service.py — Gmail SMTP email delivery and HTML templates.

If GMAIL_USER / GMAIL_APP_PASSWORD are not set, all sends are mocked
(logged but not actually delivered). This allows local development without
email credentials.

All user-controlled values (client names, notes, invoice descriptions) are
HTML-escaped before interpolation to prevent stored XSS in email clients.
"""
import html as html_lib
import logging
import smtplib
from email.mime.text import MIMEText
from email.utils import formataddr, parseaddr

from app.config import settings

logger = logging.getLogger(__name__)


async def send_email(to: str, subject: str, html: str) -> dict:
    """
    Send an HTML email via Gmail SMTP SSL.

    Returns a dict with keys:
      {sent: bool, mocked?: bool, error?: str}
    """
    if not to:
        return {"sent": False, "reason": "no recipient"}

    if not settings.gmail_user or not settings.gmail_password_clean:
        logger.info("[MOCKED EMAIL] to=%s subject=%s", to, subject)
        return {"sent": True, "mocked": True}

    try:
        msg = MIMEText(html, "html", "utf-8")
        msg["Subject"] = subject

        # Parse "Name <addr>" or fall back to bare addr
        sender_name, sender_addr = parseaddr(settings.effective_sender_email)
        if not sender_addr:
            sender_addr = settings.gmail_user
        msg["From"] = formataddr((sender_name or "Atelier", sender_addr))
        msg["To"] = to

        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=15) as smtp:
            smtp.login(settings.gmail_user, settings.gmail_password_clean)
            smtp.sendmail(settings.gmail_user, [to], msg.as_string())

        return {"sent": True}
    except Exception as exc:
        logger.error("Gmail SMTP send failed to=%s: %s", to, exc)
        return {"sent": False, "error": str(exc)}


def send_email_sync(to: str, subject: str, html: str) -> None:
    """
    Synchronous wrapper for use by APScheduler jobs and FastAPI BackgroundTasks.
    Runs the async send_email in a fresh event loop.
    """
    import asyncio
    try:
        asyncio.run(send_email(to, subject, html))
    except Exception as exc:
        logger.error("send_email_sync failed: %s", exc)


# ── HTML templates ─────────────────────────────────────────────────────────────

def meeting_html(title: str, when_human: str, meet_link: str, notes: str = "") -> str:
    """
    Generate styled HTML for meeting invite / reminder emails.
    All user-supplied values are HTML-escaped.
    """
    title = html_lib.escape(title or "")
    when_human = html_lib.escape(when_human or "")
    meet_link_safe = html_lib.escape(meet_link or "", quote=True)
    notes = html_lib.escape(notes or "")
    return f"""
    <div style="font-family:Georgia,serif;max-width:560px;margin:0 auto;padding:24px;background:#FDFBF7;color:#1A1918">
      <p style="letter-spacing:.2em;color:#A3523B;font-size:12px;text-transform:uppercase">Atelier</p>
      <h2 style="font-family:Georgia,serif;margin:8px 0 16px">{title}</h2>
      <p style="margin:4px 0">When: <strong>{when_human}</strong></p>
      <p style="margin:4px 0">Join: <a href="{meet_link_safe}" style="color:#A3523B">{meet_link_safe}</a></p>
      {f'<p style="margin-top:16px;color:#4A4845">{notes}</p>' if notes else ''}
      <hr style="border:0;border-top:1px solid #EAE5DA;margin:24px 0" />
      <p style="font-size:12px;color:#6B6761">Sent via Atelier</p>
    </div>"""


def invoice_html(client_name: str, items: list) -> str:
    """
    Generate styled HTML for invoice update emails.
    All user-supplied values are HTML-escaped.
    """
    rows = ""
    total_pending = 0.0
    for it in items:
        color = "#5C6B5D" if it["status"] == "cleared" else "#B38A58"
        desc = html_lib.escape(it["description"] or "")
        status = html_lib.escape(it["status"] or "")
        rows += (
            f"<tr>"
            f"<td style='padding:10px 0;border-bottom:1px solid #EAE5DA'>{desc}</td>"
            f"<td style='padding:10px 0;border-bottom:1px solid #EAE5DA;text-align:right'>₹{it['amount']:.2f}</td>"
            f"<td style='padding:10px 0;border-bottom:1px solid #EAE5DA;color:{color};"
            f"text-transform:uppercase;font-size:11px;letter-spacing:.1em;text-align:right'>{status}</td>"
            f"</tr>"
        )
        if it["status"] != "cleared":
            total_pending += float(it["amount"])

    client_name = html_lib.escape(client_name or "")
    return f"""
    <div style="font-family:Georgia,serif;max-width:560px;margin:0 auto;padding:24px;background:#FDFBF7;color:#1A1918">
      <p style="letter-spacing:.2em;color:#A3523B;font-size:12px;text-transform:uppercase">Atelier — Invoice update</p>
      <h2 style="margin:8px 0 16px">Hello {client_name},</h2>
      <p>Your invoice has been updated. Latest summary below.</p>
      <table style="width:100%;border-collapse:collapse;margin-top:16px;font-family:Arial,sans-serif;font-size:14px">{rows}</table>
      <p style="margin-top:16px;font-family:Arial,sans-serif">Pending balance: <strong>₹{total_pending:.2f}</strong></p>
      <hr style="border:0;border-top:1px solid #EAE5DA;margin:24px 0" />
      <p style="font-size:12px;color:#6B6761;font-family:Arial,sans-serif">Sent via Atelier</p>
    </div>"""
