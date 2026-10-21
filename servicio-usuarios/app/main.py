"""Microservicio de Usuarios — Python + FastAPI + SQLAlchemy + PostgreSQL.

Además de administrar usuarios, es el servicio de autenticación: registra cuentas,
inicia sesión y emite los tokens JWT que usan los demás microservicios.
"""
import logging
import os
import time
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Response, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

from .actividad import registrar_evento
from .database import Base, SessionLocal, engine, get_db
from .models import Usuario
from .schemas import Login, Registro, TokenRespuesta, UsuarioActualizar, UsuarioCrear, UsuarioRespuesta
from .seguridad import (
    JWT_EXPIRA_MIN,
    Identidad,
    crear_token,
    hashear_password,
    identidad_actual,
    requiere_rol,
    verificar_password,
)

log = logging.getLogger("uvicorn.error")

DB = Annotated[Session, Depends(get_db)]
Admin = Annotated[Identidad, Depends(requiere_rol("admin"))]
Autenticado = Annotated[Identidad, Depends(identidad_actual)]

ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "admin@tienda.com")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "Admin2026!")
CLIENTE_PASSWORD_DEMO = "Cliente2026"

CLIENTES_INICIALES = [
    {"nombre": "María Pérez", "email": "maria.perez@gmail.com", "telefono": "0414-1234567", "ciudad": "Valencia"},
    {"nombre": "José Rodríguez", "email": "jose.rodriguez@gmail.com", "telefono": "0424-7654321", "ciudad": "Maracay"},
    {"nombre": "Ana Gómez", "email": "ana.gomez@ujap.edu.ve", "telefono": "0412-5558899", "ciudad": "San Diego"},
]


def preparar_base_de_datos(intentos: int = 15) -> None:
    """Crea la tabla si no existe, carga clientes de ejemplo y garantiza que exista un administrador."""
    for intento in range(1, intentos + 1):
        try:
            Base.metadata.create_all(engine)
            break
        except OperationalError:
            if intento == intentos:
                raise
            log.warning("PostgreSQL no disponible (intento %d), reintentando...", intento)
            time.sleep(2)

    with SessionLocal() as db:
        if db.scalar(select(func.count()).select_from(Usuario)) == 0:
            hash_demo = hashear_password(CLIENTE_PASSWORD_DEMO)
            db.add_all(Usuario(**datos, rol="cliente", password_hash=hash_demo) for datos in CLIENTES_INICIALES)
            log.info("Clientes de ejemplo creados")
        if db.scalar(select(func.count()).select_from(Usuario).where(Usuario.rol == "admin")) == 0:
            db.add(Usuario(nombre="Administrador", email=ADMIN_EMAIL, rol="admin", password_hash=hashear_password(ADMIN_PASSWORD)))
            log.info("Administrador creado: %s", ADMIN_EMAIL)
        db.commit()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    preparar_base_de_datos()
    yield


app = FastAPI(
    title="Servicio de Usuarios",
    description=(
        "Microservicio Python/FastAPI con PostgreSQL — Proyecto Final LPR07304.\n\n"
        "Para probar las rutas protegidas: haz login en `POST /api/auth/login`, copia el `access_token` "
        "y pégalo en el botón **Authorize**."
    ),
    version="2.0.0",
    lifespan=lifespan,
    # La documentación queda bajo /api/usuarios para poder abrirla a través del gateway
    docs_url="/api/usuarios/docs",
    redoc_url=None,
    openapi_url="/api/usuarios/openapi.json",
)


def buscar_usuario(db: Session, usuario_id: int) -> Usuario:
    usuario = db.get(Usuario, usuario_id)
    if usuario is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=f"Usuario {usuario_id} no encontrado")
    return usuario


def guardar(db: Session, email: str | None) -> None:
    """Confirma la transacción; si el email ya existe responde 409 en lugar de un error 500."""
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, detail=f"Ya existe un usuario con el email {email}")


def respuesta_token(usuario: Usuario) -> TokenRespuesta:
    return TokenRespuesta(
        access_token=crear_token(usuario),
        expira_en_min=JWT_EXPIRA_MIN,
        usuario=UsuarioRespuesta.model_validate(usuario),
    )


@app.get("/health", tags=["Estado"])
def health():
    return {"status": "ok", "servicio": "usuarios", "lenguaje": "Python/FastAPI"}


# ─────────────────────────── Autenticación ───────────────────────────

@app.post("/api/auth/login", response_model=TokenRespuesta, tags=["Autenticación"])
def login(datos: Login, db: DB, tareas: BackgroundTasks):
    usuario = db.scalar(select(Usuario).where(Usuario.email == datos.email))
    if not verificar_password(datos.password, usuario.password_hash if usuario else None):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Email o contraseña incorrectos")
    tareas.add_task(registrar_evento, "SESION_INICIADA", f"{usuario.nombre} inició sesión ({usuario.rol})", {"usuario_id": usuario.id})
    return respuesta_token(usuario)


@app.post("/api/auth/registro", response_model=TokenRespuesta, status_code=status.HTTP_201_CREATED, tags=["Autenticación"])
def registro(datos: Registro, db: DB, tareas: BackgroundTasks):
    usuario = Usuario(**datos.model_dump(exclude={"password"}), rol="cliente", password_hash=hashear_password(datos.password))
    db.add(usuario)
    guardar(db, datos.email)
    db.refresh(usuario)
    tareas.add_task(registrar_evento, "USUARIO_REGISTRADO", f"Nueva cuenta de cliente: {usuario.nombre}", {"usuario_id": usuario.id})
    return respuesta_token(usuario)


@app.get("/api/auth/yo", response_model=UsuarioRespuesta, tags=["Autenticación"])
def yo(identidad: Autenticado, db: DB):
    if identidad.usuario_id is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="El token no pertenece a un usuario")
    return buscar_usuario(db, identidad.usuario_id)


# ─────────────────────────── Usuarios ───────────────────────────

@app.get("/api/usuarios", response_model=list[UsuarioRespuesta], tags=["Usuarios"])
def listar_usuarios(_admin: Admin, db: DB):
    return db.scalars(select(Usuario).order_by(Usuario.id)).all()


@app.get("/api/usuarios/{usuario_id}", response_model=UsuarioRespuesta, tags=["Usuarios"])
def obtener_usuario(usuario_id: int, identidad: Autenticado, db: DB):
    # Lo puede ver: un administrador, el propio usuario o otro microservicio (p. ej. pedidos)
    if not (identidad.es_admin or identidad.rol == "servicio" or identidad.usuario_id == usuario_id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="No tienes permiso para ver este usuario")
    return buscar_usuario(db, usuario_id)


@app.post("/api/usuarios", response_model=UsuarioRespuesta, status_code=status.HTTP_201_CREATED, tags=["Usuarios"])
def crear_usuario(datos: UsuarioCrear, _admin: Admin, db: DB, tareas: BackgroundTasks):
    usuario = Usuario(**datos.model_dump(exclude={"password"}), password_hash=hashear_password(datos.password))
    db.add(usuario)
    guardar(db, datos.email)
    db.refresh(usuario)
    tareas.add_task(registrar_evento, "USUARIO_CREADO", f"Nuevo usuario: {usuario.nombre} ({usuario.rol})", {"usuario_id": usuario.id})
    return usuario


@app.put("/api/usuarios/{usuario_id}", response_model=UsuarioRespuesta, tags=["Usuarios"])
def actualizar_usuario(usuario_id: int, datos: UsuarioActualizar, identidad: Autenticado, db: DB, tareas: BackgroundTasks):
    if not (identidad.es_admin or identidad.usuario_id == usuario_id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Solo puedes modificar tu propia cuenta")
    if datos.rol is not None and not identidad.es_admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Solo un administrador puede cambiar el rol")

    usuario = buscar_usuario(db, usuario_id)
    cambios = datos.model_dump(exclude_unset=True, exclude_none=True)
    if "password" in cambios:
        usuario.password_hash = hashear_password(cambios.pop("password"))
    for campo, valor in cambios.items():
        setattr(usuario, campo, valor)
    guardar(db, datos.email)
    db.refresh(usuario)
    tareas.add_task(registrar_evento, "USUARIO_ACTUALIZADO", f"Usuario actualizado: {usuario.nombre}", {"usuario_id": usuario.id})
    return usuario


@app.delete("/api/usuarios/{usuario_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["Usuarios"])
def eliminar_usuario(usuario_id: int, admin: Admin, db: DB, tareas: BackgroundTasks):
    if admin.usuario_id == usuario_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="No puedes eliminar tu propia cuenta de administrador")
    usuario = buscar_usuario(db, usuario_id)
    db.delete(usuario)
    db.commit()
    tareas.add_task(registrar_evento, "USUARIO_ELIMINADO", f"Usuario eliminado: {usuario.nombre}", {"usuario_id": usuario_id})
    return Response(status_code=status.HTTP_204_NO_CONTENT)
