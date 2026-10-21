"""Autenticación: contraseñas con bcrypt y tokens JWT (HS256).

Este servicio EMITE los tokens al iniciar sesión. Los otros tres microservicios los VERIFICAN
con el mismo secreto (JWT_SECRET), sin tener que consultar a este servicio en cada petición.
"""
import os
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
    """Token de un usuario: sub = id, más nombre, email y rol (admin | cliente)."""
    return _firmar({"sub": str(usuario.id), "nombre": usuario.nombre, "email": usuario.email, "rol": usuario.rol}, JWT_EXPIRA_MIN)


def crear_token_servicio() -> str:
    """Token corto que usa este servicio para llamar a otros microservicios."""
    return _firmar({"sub": "servicio-usuarios", "rol": "servicio"}, 5)


@dataclass
class Identidad:
    sub: str
    rol: str
    nombre: str | None = None

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
        datos = jwt.decode(credenciales.credentials, JWT_SECRET, algorithms=[JWT_ALGORITMO])
    except jwt.ExpiredSignatureError:
        raise _no_autorizado("El token expiró, inicia sesión de nuevo")
    except jwt.InvalidTokenError:
        raise _no_autorizado("Token inválido")
    if not datos.get("sub") or not datos.get("rol"):
        raise _no_autorizado("Token inválido")
    return Identidad(sub=datos["sub"], rol=datos["rol"], nombre=datos.get("nombre"))


def requiere_rol(*roles: str):
    """Dependencia que exige un token válido con alguno de los roles indicados."""

    def dependencia(identidad: Annotated[Identidad, Depends(identidad_actual)]) -> Identidad:
        if identidad.rol not in roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, detail="No tienes permiso para esta operación")
        return identidad

    return dependencia
