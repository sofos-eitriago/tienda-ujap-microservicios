"""Modelos ORM: tablas del servicio de usuarios en PostgreSQL."""
from datetime import datetime

from sqlalchemy import DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base


class Usuario(Base):
    __tablename__ = "usuarios"

    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(100))
    email: Mapped[str] = mapped_column(String(150), unique=True, index=True)
    telefono: Mapped[str | None] = mapped_column(String(30))
    ciudad: Mapped[str | None] = mapped_column(String(80))
    rol: Mapped[str] = mapped_column(String(20), default="cliente", server_default="cliente")
    # Nunca se guarda la contraseña: solo su hash bcrypt
    password_hash: Mapped[str] = mapped_column(String(100))
    # Va dentro de cada token. Al subirla, todos los tokens anteriores del usuario dejan de valer
    # (cambio de contraseña o de rol, o un administrador que cierra sus sesiones).
    version_sesion: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class TokenRevocado(Base):
    """Tokens de sesiones cerradas con "Cerrar sesión". Se guardan solo hasta que expiran."""
    __tablename__ = "tokens_revocados"

    jti: Mapped[str] = mapped_column(String(32), primary_key=True)
    expira_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
