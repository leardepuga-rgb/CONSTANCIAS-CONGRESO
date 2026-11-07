"""Envío de constancias por correo (SMTP)."""
from __future__ import annotations

import re
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def is_valid_email(value: str) -> bool:
    return bool(EMAIL_RE.match(str(value).strip()))


def fill_template(text: str, **fields) -> str:
    """Reemplaza {nombre}, {rol}, {evento} sin fallar si falta alguno."""
    for k, v in fields.items():
        text = text.replace("{" + k + "}", str(v))
    return text


def _connect(smtp: dict, password: str):
    host, port = smtp["host"], int(smtp["port"])
    ctx = ssl.create_default_context()
    if port == 465:
        server = smtplib.SMTP_SSL(host, port, context=ctx, timeout=30)
    else:
        server = smtplib.SMTP(host, port, timeout=30)
        server.ehlo()
        server.starttls(context=ctx)
        server.ehlo()
    server.login(smtp["user"], password)
    return server


def test_connection(smtp: dict, password: str) -> str:
    """Devuelve 'ok' o el mensaje de error."""
    try:
        server = _connect(smtp, password)
        server.quit()
        return "ok"
    except Exception as e:  # noqa: BLE001
        return f"{type(e).__name__}: {e}"


def build_message(smtp: dict, to: str, subject: str, body: str,
                  pdf: bytes, filename: str) -> EmailMessage:
    msg = EmailMessage()
    msg["From"] = formataddr((smtp.get("from_name", ""), smtp["user"]))
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)
    msg.add_attachment(pdf, maintype="application", subtype="pdf", filename=filename)
    return msg


def send_many(smtp: dict, password: str, items: list[dict], progress=None) -> list[dict]:
    """items: [{to, subject, body, pdf, filename}] -> [{to, status, detail}]

    Usa una sola conexión y la reabre si el servidor la corta.
    """
    results: list[dict] = []
    server = None
    try:
        server = _connect(smtp, password)
        for i, it in enumerate(items, 1):
            try:
                msg = build_message(smtp, it["to"], it["subject"], it["body"], it["pdf"], it["filename"])
                try:
                    server.send_message(msg)
                except (smtplib.SMTPServerDisconnected, smtplib.SMTPSenderRefused):
                    server = _connect(smtp, password)
                    server.send_message(msg)
                results.append({"to": it["to"], "status": "Enviado", "detail": ""})
            except Exception as e:  # noqa: BLE001
                results.append({"to": it["to"], "status": "Error", "detail": f"{type(e).__name__}: {e}"})
            if progress:
                progress(i, len(items))
    except Exception as e:  # noqa: BLE001  (falla el login/conexión)
        done = {r["to"] for r in results}
        for it in items:
            if it["to"] not in done:
                results.append({"to": it["to"], "status": "Error", "detail": f"Conexión: {e}"})
    finally:
        if server:
            try:
                server.quit()
            except Exception:  # noqa: BLE001
                pass
    return results
