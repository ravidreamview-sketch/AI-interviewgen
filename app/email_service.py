import os
import smtplib
import json
import logging
import urllib.request
import urllib.error
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime, timezone
from typing import Dict, Any, Optional

logger = logging.getLogger("ravi.email_service")


def get_base_app_url() -> str:
    """
    Resolves the canonical base application URL for invitation links.
    Priority:
    1. Explicit APP_URL configuration (APP_URL, NEXT_PUBLIC_APP_URL, PUBLIC_URL)
    2. Vercel Preview deployment (VERCEL_ENV=preview or ENV=preview):
       resolves PREVIEW_APP_URL or deployment-specific VERCEL_URL.
    3. Production deployment (VERCEL_ENV=production or ENVIRONMENT/ENV in ['production', 'prod']):
       resolves VERCEL_PROJECT_PRODUCTION_URL or canonical default "https://ai-interviewgen.vercel.app".
    4. Deployment-specific VERCEL_URL (if present in other Vercel contexts).
    5. Local development fallback ("http://localhost:8000").
    Note: VERCEL=1 alone is NOT treated as proof of production.
    """
    # 1. Explicit configuration takes absolute precedence
    for env_key in ("APP_URL", "NEXT_PUBLIC_APP_URL", "PUBLIC_URL"):
        val = (os.environ.get(env_key) or "").strip()
        if val:
            if not val.startswith("http://") and not val.startswith("https://"):
                val = f"https://{val}"
            return val.rstrip("/")

    vercel_env = (os.environ.get("VERCEL_ENV") or "").lower().strip()
    generic_env = (os.environ.get("ENVIRONMENT") or os.environ.get("ENV") or "").lower().strip()

    # 2. Preview deployments: use preview-specific URL
    if vercel_env == "preview" or generic_env == "preview":
        preview_url = (os.environ.get("PREVIEW_APP_URL") or os.environ.get("VERCEL_URL") or "").strip()
        if preview_url:
            if not preview_url.startswith("http://") and not preview_url.startswith("https://"):
                preview_url = f"https://{preview_url}"
            return preview_url.rstrip("/")

    # 3. Production deployments: resolve canonical production URL
    if vercel_env == "production" or generic_env in ["production", "prod"]:
        vercel_prod = (os.environ.get("VERCEL_PROJECT_PRODUCTION_URL") or "").strip()
        if vercel_prod:
            if not vercel_prod.startswith("http://") and not vercel_prod.startswith("https://"):
                vercel_prod = f"https://{vercel_prod}"
            return vercel_prod.rstrip("/")
        return "https://ai-interviewgen.vercel.app"

    # 4. Fallback for deployment-specific URL if present (without assuming production)
    vercel_url = (os.environ.get("VERCEL_URL") or "").strip()
    if vercel_url:
        if not vercel_url.startswith("http://") and not vercel_url.startswith("https://"):
            vercel_url = f"https://{vercel_url}"
        return vercel_url.rstrip("/")

    # 5. Local development fallback
    return "http://localhost:8000"


def send_invitation_email(
    to_email: str,
    invite_url: str,
    role: str = "candidate",
    expires_at: Optional[datetime] = None,
    invited_by: Optional[str] = None
) -> Dict[str, Any]:
    """
    Sends an invitation email with a secure registration link.
    Supports SMTP, Resend HTTP API, SendGrid API, or local dev/test fallback logging.
    """
    role_display = "Staff Administrator" if role == "admin" else ("Super Administrator" if role == "super_admin" else "Candidate")
    sender_name = invited_by or "The Administrator"
    expiry_text = "24 hours"
    if expires_at:
        try:
            now = datetime.now(timezone.utc)
            hours_left = max(1, int((expires_at - now).total_seconds() // 3600))
            expiry_text = f"{hours_left} hours"
        except Exception:
            pass

    subject = f"You're invited to join RaviGen AI Interview Studio ({role_display})"

    html_content = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  body {{ font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background-color: #08141E; color: #F8FAFC; margin: 0; padding: 24px; }}
  .email-container {{ max-width: 560px; margin: 0 auto; background: #112B3E; border: 1px solid #1A364E; border-radius: 14px; padding: 36px 32px; }}
  .brand {{ text-align: center; margin-bottom: 24px; }}
  .brand-title {{ font-size: 22px; font-weight: 800; color: #38BDF8; letter-spacing: -0.02em; }}
  .brand-sub {{ font-size: 11px; text-transform: uppercase; color: #94A3B8; font-family: monospace; letter-spacing: 0.15em; margin-top: 4px; }}
  .content {{ font-size: 15px; line-height: 1.6; color: #E2E8F0; margin-bottom: 28px; }}
  .role-pill {{ display: inline-block; padding: 4px 12px; background: rgba(52, 211, 153, 0.15); border: 1px solid rgba(52, 211, 153, 0.4); border-radius: 99px; font-size: 13px; font-weight: 700; color: #34D399; margin: 8px 0; }}
  .btn-wrapper {{ text-align: center; margin: 32px 0; }}
  .btn-action {{ display: inline-block; padding: 14px 28px; background: linear-gradient(135deg, #15803D 0%, #16A34A 100%); color: #FFFFFF !important; text-decoration: none; border-radius: 10px; font-weight: 700; font-size: 15px; box-shadow: 0 4px 14px rgba(22, 163, 74, 0.4); }}
  .security-notice {{ padding: 14px 16px; background: #0D2130; border-left: 3px solid #38BDF8; border-radius: 6px; font-size: 12.5px; color: #94A3B8; margin-top: 24px; }}
  .footer {{ text-align: center; margin-top: 28px; font-size: 12px; color: #64748B; }}
</style>
</head>
<body>
<div class="email-container">
  <div class="brand">
    <div class="brand-title">RaviGen AI</div>
    <div class="brand-sub">INTERVIEW STUDIO</div>
  </div>

  <div class="content">
    <p>Hello,</p>
    <p>You have been invited by <b>{sender_name}</b> to join <b>RaviGen AI Interview Studio</b>.</p>
    <div>
      <span class="role-pill">Role: {role_display}</span>
    </div>
    <p>To accept your invitation, activate your workspace, and securely configure your password, click the button below:</p>

    <div class="btn-wrapper">
      <a href="{invite_url}" class="btn-action" target="_blank" rel="noopener noreferrer">Accept Invitation &amp; Set Password</a>
    </div>

    <div class="security-notice">
      <b>Security Notice:</b> This single-use link is cryptographically tied to <code>{to_email}</code> and will expire in <b>{expiry_text}</b>.
      RaviGen AI will never ask for your password via email. If you did not anticipate this invitation, you can safely ignore this email.
    </div>

    <p style="margin-top: 20px; font-size: 12px; color: #64748B; word-break: break-all;">
      If the button above does not work, copy and paste this secure link directly into your browser:<br>
      <a href="{invite_url}" style="color: #38BDF8;">{invite_url}</a>
    </p>
  </div>

  <div class="footer">
    &copy; {datetime.now(timezone.utc).year} RaviGen AI Interview Studio. All rights reserved.
  </div>
</div>
</body>
</html>"""

    plain_content = f"""Hello,

You have been invited by {sender_name} to join RaviGen AI Interview Studio as a {role_display}.

To accept your invitation and configure your password, visit the following secure link:
{invite_url}

This single-use link will expire in {expiry_text}.
If you did not request this invitation, you can safely ignore this message.

— RaviGen AI Team
"""

    # 1. Try Resend API (if configured)
    resend_key = (os.environ.get("RESEND_API_KEY") or "").strip()
    if resend_key:
        try:
            req_data = {
                "from": os.environ.get("EMAIL_FROM") or "RaviGen AI <invitations@ai-interviewgen.vercel.app>",
                "to": [to_email],
                "subject": subject,
                "html": html_content,
                "text": plain_content
            }
            req = urllib.request.Request(
                "https://api.resend.com/emails",
                data=json.dumps(req_data).encode("utf-8"),
                headers={
                    "Authorization": f"Bearer {resend_key}",
                    "Content-Type": "application/json",
                    "User-Agent": "RaviGenAI-Mailer/1.0"
                }
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                resp_body = json.loads(resp.read().decode())
                logger.info("[EmailService] Resend email dispatched to %s (id: %s)", to_email, resp_body.get("id"))
                return {"success": True, "provider": "resend", "delivery_id": resp_body.get("id")}
        except Exception as e:
            logger.warning("[EmailService] Resend API failed, falling back to SMTP/Dev: %s", e)

    # 2. Try Standard SMTP (if configured)
    smtp_host = (os.environ.get("SMTP_HOST") or "").strip()
    if smtp_host:
        try:
            smtp_port = int(os.environ.get("SMTP_PORT", "587"))
            smtp_user = os.environ.get("SMTP_USER", "").strip()
            smtp_pass = os.environ.get("SMTP_PASSWORD", "").strip()
            smtp_from = os.environ.get("SMTP_FROM", "").strip() or smtp_user or "invitations@ravigen.ai"
            use_tls = os.environ.get("SMTP_TLS", "true").lower() in ["true", "1", "yes"]

            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = smtp_from
            msg["To"] = to_email
            msg.attach(MIMEText(plain_content, "plain"))
            msg.attach(MIMEText(html_content, "html"))

            with smtplib.SMTP(smtp_host, smtp_port, timeout=10) as server:
                if use_tls:
                    server.starttls()
                if smtp_user and smtp_pass:
                    server.login(smtp_user, smtp_pass)
                server.sendmail(smtp_from, [to_email], msg.as_string())
            
            logger.info("[EmailService] SMTP email sent to %s via %s", to_email, smtp_host)
            return {"success": True, "provider": "smtp"}
        except Exception as e:
            logger.warning("[EmailService] SMTP delivery failed: %s", e)

    # 3. Development / Safe Local Fallback
    is_prod = bool(os.environ.get("VERCEL") or os.environ.get("ENV", "").lower() in ["production", "prod"])
    if is_prod:
        logger.warning(
            "[EmailService] No active email delivery provider configured (RESEND_API_KEY or SMTP_HOST missing). "
            "Invitation email for %s could not be dispatched.",
            to_email
        )
        return {
            "success": False,
            "provider": "unconfigured",
            "message": f"Email delivery provider not configured; cannot deliver invitation to {to_email}"
        }

    # In local development mode only: log the generated link for local verification
    logger.info(
        "[EmailService: Local/Dev Mock Dispatch]\n"
        "  To: %s\n"
        "  Subject: %s\n"
        "  Link: %s\n",
        to_email, subject, invite_url
    )
    return {
        "success": True,
        "provider": "console_dev",
        "message": f"Invitation link generated and logged for {to_email}",
        "invite_url": invite_url
    }

