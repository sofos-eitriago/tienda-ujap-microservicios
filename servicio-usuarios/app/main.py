"""Microservicio de Usuarios — Python + FastAPI + SQLAlchemy + PostgreSQL.

Además de administrar usuarios, es el servicio de autenticación: registra cuentas,
inicia sesión y emite los tokens JWT que usan los demás microservicios.
"""
import logging
import os
import time
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import BackgroundTasks, Depends, FastAPI, Header, HTTPException, Response, status
from sqlalchemy import delete, func, select, text
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

from .actividad import registrar_evento
from .correo import (
    CODIGO_MAX_INTENTOS,
    CODIGO_VALIDEZ_MIN,
    codigo_correcto,
    dominio_sin_correo,
    enviar_correo,
    hash_codigo,
    nuevo_codigo,
)
from .database import Base, SessionLocal, engine, get_db
from .models import ClaveAnterior, CodigoCorreo, TokenRevocado, Usuario
from .schemas import (
    Login,
    Mensaje,
    PedirCodigo,
    Registro,
    Restablecer,
    TokenRespuesta,
    UsuarioActualizar,
    UsuarioCrear,
    UsuarioRespuesta,
    VerificarCorreo,
)
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
    "ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS email_verificado BOOLEAN NOT NULL DEFAULT TRUE",
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


def usuario_por_email(db: Session, email: str) -> Usuario | None:
    return db.scalar(select(Usuario).where(Usuario.email == email))


# ─────────────── Códigos por correo ───────────────

CODIGO_INVALIDO = "El código es incorrecto o ya venció. Revisa el correo o pide uno nuevo"


def emitir_codigo(db: Session, usuario: Usuario, proposito: str) -> str:
    """Crea un código nuevo (anulando el anterior del mismo propósito) y lo devuelve para enviarlo."""
    db.execute(delete(CodigoCorreo).where(CodigoCorreo.usuario_id == usuario.id, CodigoCorreo.proposito == proposito))
    codigo = nuevo_codigo()
    db.add(CodigoCorreo(
        usuario_id=usuario.id,
        proposito=proposito,
        codigo_hash=hash_codigo(usuario.id, proposito, codigo),
        expira_en=datetime.now(timezone.utc) + timedelta(minutes=CODIGO_VALIDEZ_MIN),
    ))
    db.commit()
    return codigo


def consumir_codigo(db: Session, usuario: Usuario | None, proposito: str, codigo: str) -> None:
    """Comprueba el código. Si es correcto lo borra (sirve una sola vez); quien llama hace el commit.
    Tras CODIGO_MAX_INTENTOS fallos el código se anula, así no se puede adivinar probando."""
    if usuario is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=CODIGO_INVALIDO)
    guardado = db.scalar(
        select(CodigoCorreo)
        .where(CodigoCorreo.usuario_id == usuario.id, CodigoCorreo.proposito == proposito)
        .with_for_update()  # dos intentos a la vez no pueden usar el mismo código
    )
    if guardado is None or guardado.expira_en < datetime.now(timezone.utc):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=CODIGO_INVALIDO)
    if not codigo_correcto(usuario.id, proposito, codigo, guardado.codigo_hash):
        guardado.intentos += 1
        if guardado.intentos >= CODIGO_MAX_INTENTOS:
            db.delete(guardado)
        db.commit()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=CODIGO_INVALIDO)
    db.delete(guardado)


# ─────────────── Contraseñas ───────────────

CLAVES_ANTERIORES = 3  # además de la actual, no se pueden repetir las 3 anteriores


def cambiar_password(db: Session, usuario: Usuario, nueva: str, tareas: BackgroundTasks) -> None:
    """Cambia la contraseña (sin hacer commit): rechaza la actual y las anteriores, guarda la
    actual en el historial, cierra todas las sesiones del usuario y le avisa por correo."""
    anteriores = db.scalars(
        select(ClaveAnterior).where(ClaveAnterior.usuario_id == usuario.id).order_by(ClaveAnterior.id.desc())
    ).all()
    if any(verificar_password(nueva, h) for h in [usuario.password_hash, *(c.password_hash for c in anteriores)]):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail=f"No puedes reutilizar la contraseña actual ni ninguna de las {CLAVES_ANTERIORES} anteriores",
        )
    db.add(ClaveAnterior(usuario_id=usuario.id, password_hash=usuario.password_hash))
    for vieja in anteriores[CLAVES_ANTERIORES - 1:]:
        db.delete(vieja)
    usuario.password_hash = hashear_password(nueva)
    usuario.version_sesion += 1
    tareas.add_task(
        enviar_correo, usuario.email, "Tu contraseña de Tienda UJAP cambió",
        f"Hola, {usuario.nombre}:\n\n"
        "La contraseña de tu cuenta acaba de cambiar y se cerraron todas tus sesiones abiertas.\n\n"
        "Si no fuiste tú, recupera tu cuenta con \"¿Olvidaste tu contraseña?\" en la página de inicio de sesión.\n",
    )


def enviar_codigo_verificacion(db: Session, usuario: Usuario, tareas: BackgroundTasks) -> None:
    codigo = emitir_codigo(db, usuario, "verificacion")
    tareas.add_task(
        enviar_correo, usuario.email, "Confirma tu correo en Tienda UJAP",
        f"Hola, {usuario.nombre}:\n\n"
        f"Tu código para activar la cuenta es: {codigo}\n\n"
        f"Vence en {CODIGO_VALIDEZ_MIN} minutos. Si no creaste una cuenta en Tienda UJAP, ignora este correo.\n",
    )


@app.get("/health", tags=["Estado"])
def health():
    return {"status": "ok", "servicio": "usuarios", "lenguaje": "Python/FastAPI"}


# ─────────────────────────── Autenticación ───────────────────────────

@app.post("/api/auth/login", response_model=TokenRespuesta, tags=["Autenticación"])
def login(datos: Login, db: DB, tareas: BackgroundTasks):
    usuario = usuario_por_email(db, datos.email)
    if not verificar_password(datos.password, usuario.password_hash if usuario else None):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Email o contraseña incorrectos")
    if not usuario.email_verificado:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Primero confirma tu correo con el código que te enviamos")
    tareas.add_task(registrar_evento, "SESION_INICIADA", f"{usuario.nombre} inició sesión ({usuario.rol})", {"usuario_id": usuario.id})
    return respuesta_token(usuario)


@app.post("/api/auth/registro", response_model=Mensaje, status_code=status.HTTP_201_CREATED, tags=["Autenticación"])
def registro(datos: Registro, db: DB, tareas: BackgroundTasks):
    """Crea la cuenta sin confirmar y envía un código al correo. La sesión se abre al confirmarlo."""
    if dominio_sin_correo(datos.email):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=f"El dominio {datos.email.rsplit('@', 1)[1]} no existe o no recibe correos")
    usuario = usuario_por_email(db, datos.email)
    if usuario is not None and usuario.email_verificado:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=f"Ya existe un usuario con el email {datos.email}")
    if usuario is None:
        usuario = Usuario(email=datos.email, rol="cliente")
        db.add(usuario)
    # Un registro sin confirmar se puede repetir: así nadie bloquea un correo ajeno registrándolo antes
    usuario.nombre, usuario.telefono, usuario.ciudad = datos.nombre, datos.telefono, datos.ciudad
    usuario.password_hash = hashear_password(datos.password)
    usuario.email_verificado = False
    guardar(db, datos.email)
    db.refresh(usuario)
    enviar_codigo_verificacion(db, usuario, tareas)
    tareas.add_task(registrar_evento, "USUARIO_REGISTRADO", f"Nueva cuenta de cliente (sin confirmar): {usuario.nombre}", {"usuario_id": usuario.id})
    return Mensaje(mensaje=f"Te enviamos un código a {usuario.email}. Escríbelo para activar tu cuenta.")


@app.post("/api/auth/verificar-correo", response_model=TokenRespuesta, tags=["Autenticación"])
def verificar_correo(datos: VerificarCorreo, db: DB, tareas: BackgroundTasks):
    """Confirma el correo con el código recibido y abre la sesión."""
    usuario = usuario_por_email(db, datos.email)
    consumir_codigo(db, usuario if usuario and not usuario.email_verificado else None, "verificacion", datos.codigo)
    usuario.email_verificado = True
    db.commit()
    tareas.add_task(registrar_evento, "CORREO_VERIFICADO", f"{usuario.nombre} confirmó su correo", {"usuario_id": usuario.id})
    return respuesta_token(usuario)


@app.post("/api/auth/reenviar-codigo", response_model=Mensaje, status_code=status.HTTP_202_ACCEPTED, tags=["Autenticación"])
def reenviar_codigo(datos: PedirCodigo, db: DB, tareas: BackgroundTasks):
    """Manda un código nuevo. Responde lo mismo exista o no la cuenta, para no revelar qué correos están registrados."""
    usuario = usuario_por_email(db, datos.email)
    if usuario is not None and not usuario.email_verificado:
        enviar_codigo_verificacion(db, usuario, tareas)
    return Mensaje(mensaje="Si hay una cuenta pendiente de confirmar con ese correo, te enviamos un código nuevo")


@app.post("/api/auth/recuperar", response_model=Mensaje, status_code=status.HTTP_202_ACCEPTED, tags=["Autenticación"])
def recuperar_password(datos: PedirCodigo, db: DB, tareas: BackgroundTasks):
    """Envía un código para elegir una contraseña nueva. Responde lo mismo exista o no la cuenta."""
    usuario = usuario_por_email(db, datos.email)
    if usuario is not None:
        codigo = emitir_codigo(db, usuario, "recuperacion")
        tareas.add_task(
            enviar_correo, usuario.email, "Recupera tu contraseña de Tienda UJAP",
            f"Hola, {usuario.nombre}:\n\n"
            f"Tu código para elegir una contraseña nueva es: {codigo}\n\n"
            f"Vence en {CODIGO_VALIDEZ_MIN} minutos. Si no lo pediste, ignora este correo: tu contraseña no cambia.\n",
        )
    return Mensaje(mensaje="Si hay una cuenta con ese correo, te enviamos un código para elegir una contraseña nueva")


@app.post("/api/auth/restablecer", response_model=Mensaje, tags=["Autenticación"])
def restablecer_password(datos: Restablecer, db: DB, tareas: BackgroundTasks):
    """Cambia la contraseña con el código recibido. Cierra todas las sesiones abiertas de la cuenta."""
    usuario = usuario_por_email(db, datos.email)
    consumir_codigo(db, usuario, "recuperacion", datos.codigo)
    # Si la contraseña nueva se rechaza, no hay commit: el código sigue sirviendo para otro intento
    cambiar_password(db, usuario, datos.password, tareas)
    usuario.email_verificado = True  # quien recibió el código demostró que el correo es suyo
    db.commit()
    tareas.add_task(registrar_evento, "CLAVE_RESTABLECIDA", f"{usuario.nombre} eligió una contraseña nueva", {"usuario_id": usuario.id})
    return Mensaje(mensaje="Listo: tu contraseña cambió. Ya puedes iniciar sesión con ella")


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
    if "password" in cambios:
        cambiar_password(db, usuario, cambios.pop("password"), tareas)
    if cambios.get("rol", usuario.rol) != usuario.rol:
        usuario.version_sesion += 1
    # Un cliente que cambia su correo tiene que confirmar el nuevo antes de volver a entrar
    # (lo que cambia un administrador se da por bueno)
    confirmar_correo = cambios.get("email", usuario.email) != usuario.email and not identidad.es_admin
    if confirmar_correo:
        usuario.email_verificado = False
        usuario.version_sesion += 1
    for campo, valor in cambios.items():
        setattr(usuario, campo, valor)
    guardar(db, datos.email)
    db.refresh(usuario)
    if confirmar_correo:
        enviar_codigo_verificacion(db, usuario, tareas)
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
