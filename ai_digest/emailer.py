from email.message import EmailMessage
import smtplib

from ai_digest.config import DigestConfig, require_send_config


def build_message(config: DigestConfig, subject: str, plain_body: str, html_body: str) -> EmailMessage:
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = config.from_email
    message["To"] = config.to_email
    message.set_content(plain_body)
    message.add_alternative(html_body, subtype="html")
    return message


def send_email(config: DigestConfig, subject: str, plain_body: str, html_body: str) -> None:
    require_send_config(config)
    message = build_message(config, subject, plain_body, html_body)
    if config.smtp_use_ssl:
        with smtplib.SMTP_SSL(config.smtp_host, config.smtp_port) as client:
            client.login(config.smtp_username, config.smtp_password)
            client.send_message(message)
        return

    with smtplib.SMTP(config.smtp_host, config.smtp_port) as client:
        if config.smtp_use_tls:
            client.starttls()
        client.login(config.smtp_username, config.smtp_password)
        client.send_message(message)
