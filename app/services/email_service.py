"""SMTP email service — used to deliver image-upload links and confirmations."""
from __future__ import annotations

from email.message import EmailMessage

import aiosmtplib

from app.config.logging_config import get_logger
from app.config.settings import get_settings

logger = get_logger(__name__)


class EmailDeliveryError(Exception):
    pass


class EmailService:
    def __init__(self) -> None:
        self._settings = get_settings().email

    async def send(
        self,
        to_address: str,
        subject: str,
        body_text: str,
        body_html: str | None = None,
    ) -> None:
        message = EmailMessage()
        message["From"] = f"{self._settings.from_name} <{self._settings.from_email}>"
        message["To"] = to_address
        message["Subject"] = subject
        message.set_content(body_text)
        if body_html:
            message.add_alternative(body_html, subtype="html")

        try:
            await aiosmtplib.send(
                message,
                hostname=self._settings.smtp_host,
                port=self._settings.smtp_port,
                username=self._settings.smtp_username or None,
                password=self._settings.smtp_password or None,
                start_tls=self._settings.use_tls,
            )
            logger.info("Email sent | to={} subject={!r}", to_address, subject)
        except Exception as exc:
            logger.exception("Email delivery failed | to={}", to_address)
            raise EmailDeliveryError(str(exc)) from exc

    async def send_upload_link(
        self,
        to_address: str,
        upload_url: str,
        appliance_type: str | None = None,
    ) -> None:
        appliance_text = f" {appliance_type}" if appliance_type else ""
        subject = "Upload a photo of your appliance — Sears Diagnostic"
        text = (
            "Hello,\n\n"
            f"To help us diagnose your{appliance_text} issue more accurately, please "
            f"upload a clear photo of the affected area using the link below:\n\n"
            f"{upload_url}\n\n"
            "This link will expire in 24 hours.\n\n"
            "Thank you,\nSears Diagnostic Team"
        )
        html = (
            f"<p>Hello,</p>"
            f"<p>To help us diagnose your{appliance_text} issue more accurately, please "
            f"upload a clear photo using the link below:</p>"
            f'<p><a href="{upload_url}">Upload your photo</a></p>'
            f"<p style=\"color:#666;font-size:12px\">This link expires in 24 hours.</p>"
            f"<p>— Sears Diagnostic Team</p>"
        )
        await self.send(to_address, subject, text, html)
