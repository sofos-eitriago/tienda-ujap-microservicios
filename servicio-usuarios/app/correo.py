"""Envío de correos por SMTP y códigos de un solo uso que se mandan por correo.

En desarrollo los correos llegan a Mailpit (http://localhost:8025): nadie recibe nada de verdad.
Con SMTP_HOST, SMTP_USUARIO, etc. apuntando a un servidor real, los correos salen a Internet.
"""
import hashlib
import hmac
import logging
import os
import secrets
import smtplib
from email.message import EmailMessage
from email.utils import make_msgid

import dns.exception
import dns.resolver

from .seguridad import JWT_SECRET

SMTP_HOST = os.getenv("SMTP_HOST", "localhost")
SMTP_PORT = int(os.getenv("SMTP_PORT", "1025"))
SMTP_USUARIO = os.getenv("SMTP_USUARIO", "")
SMTP_CLAVE = os.getenv("SMTP_CLAVE", "")
SMTP_STARTTLS = os.getenv("SMTP_STARTTLS", "false").lower() == "true"
CORREO_REMITENTE = os.getenv("CORREO_REMITENTE", "Tienda UJAP <no-responder@tienda.ujap.test>")

CODIGO_VALIDEZ_MIN = 15
CODIGO_MAX_INTENTOS = 5

log = logging.getLogger("uvicorn.error")


def enviar_correo(destino: str, asunto: str, texto: str) -> None:
    """Envía un correo de texto. Se ejecuta en segundo plano: si falla, solo queda en el log."""
    mensaje = EmailMessage()
    mensaje["From"] = CORREO_REMITENTE
    mensaje["To"] = destino
    mensaje["Subject"] = asunto
    mensaje["Message-ID"] = make_msgid(domain="tienda.ujap.test")
    mensaje.set_content(texto)
    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=10) as smtp:
            if SMTP_STARTTLS:
                smtp.starttls()
            if SMTP_USUARIO:
                smtp.login(SMTP_USUARIO, SMTP_CLAVE)
            smtp.send_message(mensaje)
    except (OSError, smtplib.SMTPException) as error:
        log.warning("No se pudo enviar el correo a %s: %s", destino, error)


# ─────────────── Códigos de un solo uso ───────────────

def nuevo_codigo() -> str:
    """Código de 6 dígitos, generado con el módulo secrets (apto para seguridad)."""
    return f"{secrets.randbelow(1_000_000):06d}"


def hash_codigo(usuario_id: int, proposito: str, codigo: str) -> str:
    """En la base de datos solo se guarda este HMAC: con una copia de la tabla no se pueden leer los códigos.
    Se mezcla con el usuario y el propósito para que un código no sirva para otra cuenta ni para otra cosa."""
    return hmac.new(JWT_SECRET.encode(), f"{usuario_id}:{proposito}:{codigo}".encode(), hashlib.sha256).hexdigest()


def codigo_correcto(usuario_id: int, proposito: str, codigo: str, hash_guardado: str) -> bool:
    return hmac.compare_digest(hash_codigo(usuario_id, proposito, codigo), hash_guardado)


# ─────────────── Dominio del correo ───────────────

def dominio_sin_correo(email: str) -> bool:
    """True si el dominio del correo seguro no puede recibir mensajes (no existe o no tiene registros MX ni A).

    Si el DNS no responde (p. ej. sin Internet) se da el correo por bueno: el código de verificación
    es la comprobación definitiva.
    """
    dominio = email.rsplit("@", 1)[1]
    resolver = dns.resolver.Resolver()
    resolver.lifetime = 3
    try:
        resolver.resolve(dominio, "MX")
        return False
    except dns.resolver.NXDOMAIN:
        return True
    except dns.resolver.NoAnswer:
        pass  # sin MX: según el estándar, el correo se entrega al registro A del dominio
    except dns.exception.DNSException:
        return False
    try:
        resolver.resolve(dominio, "A")
        return False
    except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer):
        return True
    except dns.exception.DNSException:
        return False
