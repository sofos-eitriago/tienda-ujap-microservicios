"""Comunicación con el microservicio de actividad (Go)."""
import logging
import os

import httpx

from .seguridad import crear_token_servicio

ACTIVIDAD_URL = os.getenv("ACTIVIDAD_URL", "http://localhost:8004")
log = logging.getLogger("uvicorn.error")


def registrar_evento(tipo: str, mensaje: str, datos: dict | None = None) -> None:
    """Envía un evento al servicio de actividad. Si no responde, solo se deja constancia en el log."""
    try:
        httpx.post(
            f"{ACTIVIDAD_URL}/api/eventos",
            json={"servicio": "usuarios", "tipo": tipo, "mensaje": mensaje, "datos": datos or {}},
            headers={"Authorization": f"Bearer {crear_token_servicio()}"},
            timeout=2.0,
        ).raise_for_status()
    except httpx.HTTPError as error:
        log.warning("No se pudo registrar el evento en actividad: %s", error)
