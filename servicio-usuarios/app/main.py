"""Microservicio de Usuarios — Python + FastAPI + SQLAlchemy + PostgreSQL.

Además de administrar usuarios, es el servicio de autenticación: registra cuentas,
inicia sesión y emite los tokens JWT que usan los demás microservicios.
"""
import logging
import os
import time
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import BackgroundTasks, Depends, FastAPI, Header, HTTPException, Response, status
from sqlalchemy import delete, func, select, text
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

from .actividad import registrar_evento
from .database import Base, SessionLocal, engine, get_db
from .models import TokenRevocado, Usuario
from .schemas import Login, Registro, TokenRespuesta, UsuarioActualizar, UsuarioCrear, UsuarioRespuesta
from .seguridad import (
    JWT_EXPIRA_MIN,
    Identidad,
    TokenInvalido,
    crear_token,
    decodificar_token,
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

# create_all crea las tablas nuevas, pero no agrega columnas a una tabla que ya existía:
# estas sentencias ponen al día una base de datos creada con una versión anterior.
COLUMNAS_NUEVAS = [
    "ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS version_sesion INTEGER NOT NULL DEFAULT 0",
]


def preparar_base_de_datos(intentos: int = 15) -> None:
    """Crea las tablas si no existen, carga clientes de ejemplo y garantiza que exista un administrador."""
    for intento in range(1, intentos + 1):
        try:
            Base.metadata.create_all(engine)
            with engine.begin() as conexion:
                for sentencia in COLUMNAS_NUEVAS:
                    conexion.execute(text(sentencia))
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


@app.post("/api/auth/logout", status_code=status.HTTP_204_NO_CONTENT, tags=["Autenticación"])
def logout(identidad: Autenticado, db: DB, tareas: BackgroundTasks):
    """Cierra la sesión: este token deja de valer en el acto (las demás sesiones del usuario siguen)."""
    if identidad.jti is None or identidad.usuario_id is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Este token no corresponde a una sesión de usuario")
    # De paso se borran los tokens revocados que ya expiraron: no hace falta recordarlos
    db.execute(delete(TokenRevocado).where(TokenRevocado.expira_en < func.now()))
    db.merge(TokenRevocado(jti=identidad.jti, expira_en=identidad.expira))
    db.commit()
    tareas.add_task(registrar_evento, "SESION_CERRADA", f"{identidad.nombre} cerró sesión", {"usuario_id": identidad.usuario_id})
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.get("/interno/verificar", status_code=status.HTTP_204_NO_CONTENT, include_in_schema=False)
def verificar_sesion(db: DB, authorization: Annotated[str | None, Header()] = None):
    """Lo consulta el gateway (auth_request) antes de cada petición a la API: 204 deja pasar, 401 la rechaza.

    No está bajo /api, así que no se puede llamar desde fuera de Docker. La cabecera X-Motivo le dice
    al gateway qué mensaje mostrar.
    """
    if authorization is None:
        # Sin token: pasa, y cada microservicio decide si la ruta es pública (p. ej. el catálogo)
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    def rechazar(motivo: str) -> Response:
        return Response(status_code=status.HTTP_401_UNAUTHORIZED, headers={"X-Motivo": motivo})

    esquema, _, token = authorization.partition(" ")
    if esquema.lower() != "bearer" or not token:
        return rechazar("invalido")
    try:
        datos = decodificar_token(token)
    except TokenInvalido as error:
        return rechazar(error.motivo)
    if not datos["sub"].isdigit():
        return rechazar("invalido")  # los tokens de servicio solo viajan dentro de Docker
    usuario = db.get(Usuario, int(datos["sub"]))
    if (usuario is None
            or datos.get("ver", 0) != usuario.version_sesion
            or (datos.get("jti") and db.get(TokenRevocado, datos["jti"]) is not None)):
        return rechazar("revocado")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


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
    # Con otra contraseña u otro rol, los tokens que ya tenía el usuario dejan de valer
    if "password" in cambios or cambios.get("rol", usuario.rol) != usuario.rol:
        usuario.version_sesion += 1
    if "password" in cambios:
        usuario.password_hash = hashear_password(cambios.pop("password"))
    for campo, valor in cambios.items():
        setattr(usuario, campo, valor)
    guardar(db, datos.email)
    db.refresh(usuario)
    tareas.add_task(registrar_evento, "USUARIO_ACTUALIZADO", f"Usuario actualizado: {usuario.nombre}", {"usuario_id": usuario.id})
    return usuario


@app.post("/api/usuarios/{usuario_id}/cerrar-sesiones", status_code=status.HTTP_204_NO_CONTENT, tags=["Usuarios"])
def cerrar_sesiones(usuario_id: int, _admin: Admin, db: DB, tareas: BackgroundTasks):
    """El administrador cierra todas las sesiones abiertas de un usuario (p. ej. si le robaron la cuenta)."""
    usuario = buscar_usuario(db, usuario_id)
    usuario.version_sesion += 1
    db.commit()
    tareas.add_task(registrar_evento, "SESIONES_CERRADAS", f"Se cerraron todas las sesiones de {usuario.nombre}", {"usuario_id": usuario_id})
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.delete("/api/usuarios/{usuario_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["Usuarios"])
def eliminar_usuario(usuario_id: int, admin: Admin, db: DB, tareas: BackgroundTasks):
    if admin.usuario_id == usuario_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="No puedes eliminar tu propia cuenta de administrador")
    usuario = buscar_usuario(db, usuario_id)
    db.delete(usuario)
    db.commit()
    tareas.add_task(registrar_evento, "USUARIO_ELIMINADO", f"Usuario eliminado: {usuario.nombre}", {"usuario_id": usuario_id})
    return Response(status_code=status.HTTP_204_NO_CONTENT)
