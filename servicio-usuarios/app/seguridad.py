"""Autenticación: contraseñas con bcrypt y tokens JWT (HS256).

Este servicio EMITE los tokens al iniciar sesión. Los otros tres microservicios los VERIFICAN
con el mismo secreto (JWT_SECRET). Además, el gateway consulta a este servicio en cada petición
con token (ruta interna /interno/verificar) para que una sesión cerrada deje de valer al instante.
"""
import os
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Annotated

import bcrypt
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

JWT_SECRET = os.getenv("JWT_SECRET", "secreto-de-desarrollo-cambiar-en-produccion-2026")
JWT_ALGORITMO = "HS256"
JWT_EXPIRA_MIN = int(os.getenv("JWT_EXPIRA_MIN", "60"))

if len(JWT_SECRET) < 32:
    raise RuntimeError("JWT_SECRET debe tener al menos 32 caracteres")

# Hash de referencia: se usa para que un email inexistente tarde lo mismo que una contraseña incorrecta
_HASH_FICTICIO = bcrypt.hashpw(b"contrasena-ficticia", bcrypt.gensalt()).decode()


def hashear_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verificar_password(password: str, hash_guardado: str | None) -> bool:
    try:
        return bcrypt.checkpw(password.encode(), (hash_guardado or _HASH_FICTICIO).encode()) and hash_guardado is not None
    except ValueError:
        return False


def _firmar(datos: dict, minutos: int) -> str:
    ahora = datetime.now(timezone.utc)
    return jwt.encode({**datos, "iat": ahora, "exp": ahora + timedelta(minutes=minutos)}, JWT_SECRET, algorithm=JWT_ALGORITMO)


def crear_token(usuario) -> str:
    """Token de un usuario: sub = id, más nombre, email y rol (admin | cliente).

    jti identifica a este token (para poder revocarlo solo a él) y ver es la versión de sesión
    del usuario al emitirlo (para poder revocar de una vez todos sus tokens).
    """
    return _firmar({
        "sub": str(usuario.id), "nombre": usuario.nombre, "email": usuario.email, "rol": usuario.rol,
        "jti": uuid.uuid4().hex, "ver": usuario.version_sesion,
    }, JWT_EXPIRA_MIN)


def crear_token_servicio() -> str:
    """Token corto que usa este servicio para llamar a otros microservicios."""
    return _firmar({"sub": "servicio-usuarios", "rol": "servicio"}, 5)


class TokenInvalido(Exception):
    """El token no sirve. motivo: "expirado" o "invalido" (lo usa el gateway para elegir el mensaje)."""

    def __init__(self, motivo: str, mensaje: str):
        super().__init__(mensaje)
        self.motivo = motivo
        self.mensaje = mensaje


def decodificar_token(token: str) -> dict:
    """Verifica la firma y la expiración del token y devuelve su contenido."""
    try:
        datos = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITMO], options={"require": ["exp"]})
    except jwt.ExpiredSignatureError:
        raise TokenInvalido("expirado", "El token expiró, inicia sesión de nuevo")
    except jwt.InvalidTokenError:
        raise TokenInvalido("invalido", "Token inválido")
    if not datos.get("sub") or not datos.get("rol"):
        raise TokenInvalido("invalido", "Token inválido")
    return datos


@dataclass
class Identidad:
    sub: str
    rol: str
    nombre: str | None = None
    jti: str | None = None
    expira: datetime | None = None

    @property
    def usuario_id(self) -> int | None:
        return int(self.sub) if self.sub.isdigit() else None

    @property
    def es_admin(self) -> bool:
        return self.rol == "admin"


_esquema = HTTPBearer(auto_error=False, description="Token JWT obtenido en POST /api/auth/login")


def _no_autorizado(mensaje: str) -> HTTPException:
    return HTTPException(status.HTTP_401_UNAUTHORIZED, detail=mensaje, headers={"WWW-Authenticate": "Bearer"})


def identidad_actual(credenciales: Annotated[HTTPAuthorizationCredentials | None, Depends(_esquema)]) -> Identidad:
    if credenciales is None:
        raise _no_autorizado("Falta el token de acceso (Authorization: Bearer <token>)")
    try:
        datos = decodificar_token(credenciales.credentials)
    except TokenInvalido as error:
        raise _no_autorizado(error.mensaje)
    return Identidad(sub=datos["sub"], rol=datos["rol"], nombre=datos.get("nombre"), jti=datos.get("jti"),
                     expira=datetime.fromtimestamp(datos["exp"], timezone.utc))


def requiere_rol(*roles: str):
    """Dependencia que exige un token válido con alguno de los roles indicados."""

    def dependencia(identidad: Annotated[Identidad, Depends(identidad_actual)]) -> Identidad:
        if identidad.rol not in roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, detail="No tienes permiso para esta operación")
        return identidad

    return dependencia
