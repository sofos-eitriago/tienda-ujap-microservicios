"""Modelo ORM: tabla "usuarios" en PostgreSQL."""
from datetime import datetime

from sqlalchemy import DateTime, String, func
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
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
