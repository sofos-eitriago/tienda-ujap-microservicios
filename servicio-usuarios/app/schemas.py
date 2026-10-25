"""Esquemas Pydantic: validan lo que entra y definen lo que sale de la API."""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field

Rol = Literal["admin", "cliente"]
Password = Field(min_length=8, max_length=72, description="Entre 8 y 72 caracteres")


class Registro(BaseModel):
    """Lo que envía una persona al crear su propia cuenta (siempre queda como cliente)."""
    nombre: str = Field(min_length=2, max_length=100)
    email: EmailStr
    password: str = Password
    telefono: str | None = Field(default=None, max_length=30)
    ciudad: str | None = Field(default=None, max_length=80)


class UsuarioCrear(Registro):
    """Lo que envía un administrador: además puede elegir el rol."""
    rol: Rol = "cliente"


class UsuarioActualizar(BaseModel):
    nombre: str | None = Field(default=None, min_length=2, max_length=100)
    email: EmailStr | None = None
    telefono: str | None = Field(default=None, max_length=30)
    ciudad: str | None = Field(default=None, max_length=80)
    password: str | None = Field(default=None, min_length=8, max_length=72)
    rol: Rol | None = None


class Login(BaseModel):
    email: EmailStr
    password: str


Codigo = Field(pattern=r"^\d{6}$", description="Código de 6 dígitos que llegó por correo")


class VerificarCorreo(BaseModel):
    email: EmailStr
    codigo: str = Codigo


class PedirCodigo(BaseModel):
    email: EmailStr


class Restablecer(BaseModel):
    """Nueva contraseña, con el código que llegó al pedir recuperarla."""
    email: EmailStr
    codigo: str = Codigo
    password: str = Password


class Mensaje(BaseModel):
    mensaje: str


class UsuarioRespuesta(BaseModel):
    # from_attributes permite convertir directamente el objeto de SQLAlchemy a JSON
    model_config = ConfigDict(from_attributes=True)

    id: int
    nombre: str
    email: str
    telefono: str | None
    ciudad: str | None
    rol: str
    email_verificado: bool
    creado_en: datetime


class TokenRespuesta(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expira_en_min: int
    usuario: UsuarioRespuesta
