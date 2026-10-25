"""Pruebas de extremo a extremo del Proyecto Final.

Prueban el sistema completo a través del API Gateway, igual que lo usaría el frontend:
autenticación JWT, permisos por rol, CRUD de los 4 microservicios, comunicación entre ellos,
pedidos con varios productos, compensación de stock, concurrencia y eventos.

Uso (con el sistema levantado con `docker compose up`):
    python tests/e2e.py                      # usa http://tienda.ujap.test
    python tests/e2e.py http://localhost     # otra dirección (p. ej. si no agregaste el nombre a hosts)

Solo usa la biblioteca estándar de Python 3.10+. Al terminar elimina los datos que creó.
"""
import base64
import hashlib
import hmac
import json
import socket
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path



def direccion_por_defecto() -> str:
    """http://tienda.ujap.test si el nombre está en el archivo hosts; si no, avisa y usa http://localhost."""
    try:
        socket.gethostbyname("tienda.ujap.test")
        return "http://tienda.ujap.test"
    except OSError:
        print("Aviso: tienda.ujap.test no está en tu archivo hosts (ver README); se usa http://localhost\n")
        return "http://localhost"


BASE = sys.argv[1].rstrip("/") if len(sys.argv) > 1 else direccion_por_defecto()
SUFIJO = str(int(time.time()))
fallos = 0
total = 0
probando_limite = False  # solo la sección del límite de intentos espera respuestas 429


def leer_env() -> dict:
    """Lee las credenciales del administrador del .env del proyecto (o usa las de por defecto)."""
    valores = {"ADMIN_EMAIL": "admin@tienda.com", "ADMIN_PASSWORD": "Admin2026!",
               "JWT_SECRET": "secreto-de-desarrollo-cambiar-en-produccion-2026"}
    archivo = Path(__file__).resolve().parent.parent / ".env"
    if archivo.exists():
        for linea in archivo.read_text(encoding="utf-8-sig").splitlines():
            if "=" in linea and not linea.lstrip().startswith("#"):
                clave, valor = linea.split("=", 1)
                valores[clave.strip()] = valor.strip()
    return valores


def pedir(metodo, ruta, cuerpo=None, token=None):
    datos = json.dumps(cuerpo).encode() if cuerpo is not None else None
    req = urllib.request.Request(BASE + ruta, data=datos, method=metodo)
    if datos is not None:
        req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            texto = r.read().decode()
            es_json = "json" in r.headers.get("Content-Type", "")
            return r.status, (json.loads(texto) if texto and es_json else texto)
    except urllib.error.HTTPError as e:
        if e.code == 429 and not probando_limite:
            sys.exit("\nEl gateway está limitando los intentos de acceso (seguramente por una ejecución anterior).\n"
                     "Espera un minuto y vuelve a ejecutar las pruebas.")
        texto = e.read().decode()
        try:
            return e.code, json.loads(texto)
        except ValueError:
            return e.code, texto


def firmar_jwt(datos: dict, secreto: str) -> str:
    """JWT HS256 hecho a mano (solo biblioteca estándar), para probar tokens que no emite el sistema."""
    b64 = lambda b: base64.urlsafe_b64encode(b).rstrip(b"=")
    cuerpo = b64(json.dumps({"alg": "HS256", "typ": "JWT"}).encode()) + b"." + b64(json.dumps(datos).encode())
    return (cuerpo + b"." + b64(hmac.new(secreto.encode(), cuerpo, hashlib.sha256).digest())).decode()


def comprobar(nombre, condicion, detalle=""):
    global fallos, total
    total += 1
    print(("  OK    " if condicion else "  FALLA ") + nombre + ("" if condicion else f"\n          -> {detalle}"))
    if not condicion:
        fallos += 1


def detalle(cuerpo) -> str:
    return cuerpo.get("detail", "") if isinstance(cuerpo, dict) else str(cuerpo)


def stock(producto_id) -> int:
    return pedir("GET", f"/api/productos/{producto_id}")[1]["stock"]


def puerto_abierto(puerto: int) -> bool:
    with socket.socket() as s:
        s.settimeout(1)
        return s.connect_ex(("127.0.0.1", puerto)) == 0


env = leer_env()

print(f"Probando {BASE}\n")
print("== Estado, frontend y puertos")
for s in ["usuarios", "productos", "pedidos", "actividad"]:
    st, b = pedir("GET", f"/estado/{s}")
    comprobar(f"/estado/{s} -> 200 ({b.get('lenguaje') if isinstance(b, dict) else b})", st == 200, b)
st, html = pedir("GET", "/")
comprobar("GET / sirve el frontend", st == 200 and "Tienda UJAP" in html)
st, docs = pedir("GET", "/api/usuarios/docs")
comprobar("Swagger de usuarios disponible por el gateway", st == 200 and "swagger" in docs.lower())
cerrados = [p for p in (8001, 8002, 8003, 8004) if not puerto_abierto(p)]
comprobar("los microservicios NO publican puertos (8001-8004 cerrados)", len(cerrados) == 4, f"abiertos: {set((8001, 8002, 8003, 8004)) - set(cerrados)}")

print("== Autenticación (JWT)")
st, b = pedir("POST", "/api/auth/login", {"email": env["ADMIN_EMAIL"], "password": env["ADMIN_PASSWORD"]})
comprobar("login de administrador -> 200 con token", st == 200 and b.get("access_token") and b["usuario"]["rol"] == "admin", (st, b))
ADMIN = b.get("access_token")
admin_id = b.get("usuario", {}).get("id")
st, b = pedir("POST", "/api/auth/login", {"email": env["ADMIN_EMAIL"], "password": "incorrecta"})
comprobar("contraseña incorrecta -> 401", st == 401, (st, b))
st, b = pedir("POST", "/api/auth/login", {"email": f"nadie{SUFIJO}@gmail.com", "password": "loquesea123"})
comprobar("email inexistente -> 401 (mismo mensaje)", st == 401 and detalle(b) == "Email o contraseña incorrectos", (st, b))
email_cliente = f"cliente{SUFIJO}@gmail.com"
st, b = pedir("POST", "/api/auth/registro", {"nombre": "Cliente Prueba", "email": email_cliente, "password": "Prueba2026", "ciudad": "Valencia"})
comprobar("registro de cliente -> 201 con token y rol cliente", st == 201 and b["usuario"]["rol"] == "cliente", (st, b))
CLIENTE = b.get("access_token")
cliente_id = b.get("usuario", {}).get("id")
st, b = pedir("POST", "/api/auth/registro", {"nombre": "Otro", "email": f"otro{SUFIJO}@gmail.com", "password": "corta"})
comprobar("registro con contraseña corta -> 422", st == 422, (st, b))
st, b = pedir("GET", "/api/auth/yo", token=CLIENTE)
comprobar("GET /api/auth/yo devuelve al cliente", st == 200 and b.get("email") == email_cliente, (st, b))
st, b = pedir("GET", "/api/auth/yo", token=CLIENTE[:-3] + "abc")
comprobar("token alterado -> 401", st == 401, (st, b))

print("== Cierre de sesión inmediato (el gateway consulta al servicio de usuarios)")
st, b = pedir("POST", "/api/auth/login", {"email": email_cliente, "password": "Prueba2026"})
SEGUNDA_SESION = b.get("access_token")
st, b = pedir("POST", "/api/auth/logout", token=SEGUNDA_SESION)
comprobar("cerrar sesión -> 204", st == 204, (st, b))
st, b = pedir("GET", "/api/auth/yo", token=SEGUNDA_SESION)
comprobar("ese token deja de valer al instante, aunque no expiró -> 401", st == 401 and "cerrada" in detalle(b), (st, b))
st, b = pedir("GET", "/api/pedidos", token=SEGUNDA_SESION)
comprobar("tampoco vale en otro microservicio (pedidos, Java) -> 401", st == 401, (st, b))
st, b = pedir("GET", "/api/auth/yo", token=CLIENTE)
comprobar("la otra sesión del mismo cliente sigue abierta", st == 200, (st, b))
token_servicio = firmar_jwt({"sub": "servicio-pedidos", "rol": "servicio", "exp": int(time.time()) + 300}, env["JWT_SECRET"])
st, b = pedir("GET", f"/api/usuarios/{cliente_id}", token=token_servicio)
comprobar("un token de servicio no se acepta desde fuera de Docker -> 401", st == 401, (st, b))

print("== Permisos por rol")
st, _ = pedir("GET", "/api/usuarios")
comprobar("listar usuarios sin token -> 401", st == 401, st)
st, _ = pedir("GET", "/api/usuarios", token=CLIENTE)
comprobar("listar usuarios como cliente -> 403", st == 403, st)
st, _ = pedir("GET", f"/api/usuarios/{cliente_id}", token=CLIENTE)
comprobar("el cliente ve su propio usuario -> 200", st == 200, st)
st, _ = pedir("GET", f"/api/usuarios/{admin_id}", token=CLIENTE)
comprobar("el cliente NO ve a otro usuario -> 403", st == 403, st)
st, b = pedir("PUT", f"/api/usuarios/{cliente_id}", {"rol": "admin"}, token=CLIENTE)
comprobar("el cliente no puede hacerse admin -> 403", st == 403, (st, b))
st, b = pedir("PUT", f"/api/usuarios/{cliente_id}", {"telefono": "0414-0000000"}, token=CLIENTE)
comprobar("el cliente edita su teléfono -> 200", st == 200 and b.get("telefono") == "0414-0000000", (st, b))
st, _ = pedir("POST", "/api/productos", {"nombre": "X", "precio": 1}, token=CLIENTE)
comprobar("crear producto como cliente -> 403", st == 403, st)
st, _ = pedir("GET", "/api/eventos", token=CLIENTE)
comprobar("ver actividad como cliente -> 403", st == 403, st)
st, _ = pedir("GET", "/api/eventos")
comprobar("ver actividad sin token -> 401", st == 401, st)
st, _ = pedir("GET", "/api/pedidos")
comprobar("ver pedidos sin token -> 401", st == 401, st)
st, b = pedir("POST", "/api/eventos", {"servicio": "x", "tipo": "y", "mensaje": "z"}, token=ADMIN)
comprobar("POST /api/eventos desde fuera -> 403 (bloqueado en el gateway)", st == 403, (st, b))
st, b = pedir("POST", "/api/productos/aaaaaaaaaaaaaaaaaaaaaaaa/reservar", {"cantidad": 1, "referencia": "x"}, token=ADMIN)
comprobar("reservar stock desde fuera -> 403 (bloqueado en el gateway)", st == 403, (st, b))

print("== Usuarios (FastAPI + PostgreSQL)")
st, lista = pedir("GET", "/api/usuarios", token=ADMIN)
comprobar(f"listar usuarios como admin -> {len(lista)} usuarios", st == 200 and len(lista) >= 4, (st, lista))
email_nuevo = f"nuevo{SUFIJO}@gmail.com"
st, nuevo = pedir("POST", "/api/usuarios", {"nombre": "Usuario Nuevo", "email": email_nuevo, "password": "Nuevo2026"}, token=ADMIN)
comprobar("crear usuario como admin -> 201", st == 201 and nuevo.get("rol") == "cliente", (st, nuevo))
st, b = pedir("POST", "/api/auth/login", {"email": email_nuevo, "password": "Nuevo2026"})
TOKEN_NUEVO = b.get("access_token")
st, b = pedir("POST", f"/api/usuarios/{nuevo['id']}/cerrar-sesiones", token=CLIENTE)
comprobar("un cliente no puede cerrar sesiones ajenas -> 403", st == 403, (st, b))
st, b = pedir("POST", f"/api/usuarios/{nuevo['id']}/cerrar-sesiones", token=ADMIN)
st2, b2 = pedir("GET", "/api/auth/yo", token=TOKEN_NUEVO)
comprobar("el admin cierra todas las sesiones de un usuario -> su token ya no vale", st == 204 and st2 == 401, (st, b, st2, b2))
st, b = pedir("POST", "/api/usuarios", {"nombre": "Repetido", "email": email_nuevo, "password": "Nuevo2026"}, token=ADMIN)
comprobar("email duplicado -> 409", st == 409, (st, b))
st, b = pedir("POST", "/api/usuarios", {"nombre": "X", "email": "no-es-email", "password": "Nuevo2026"}, token=ADMIN)
comprobar("datos inválidos -> 422", st == 422, (st, b))
st, b = pedir("GET", "/api/usuarios/999999", token=ADMIN)
comprobar("usuario inexistente -> 404", st == 404, (st, b))
st, b = pedir("DELETE", f"/api/usuarios/{admin_id}", token=ADMIN)
comprobar("el admin no puede eliminarse a sí mismo -> 400", st == 400, (st, b))

print("== Productos (Express + MongoDB)")
st, catalogo = pedir("GET", "/api/productos")
comprobar(f"catálogo público sin token -> {len(catalogo)} productos", st == 200 and len(catalogo) >= 6, (st, catalogo))
comprobar("el catálogo no expone datos internos (movimientos)", all("movimientos" not in p for p in catalogo))
st, A = pedir("POST", "/api/productos", {"nombre": f"Prueba A {SUFIJO}", "precio": 10.25, "stock": 5}, token=ADMIN)
st2, B = pedir("POST", "/api/productos", {"nombre": f"Prueba B {SUFIJO}", "precio": 3, "stock": 2}, token=ADMIN)
comprobar("crear productos como admin -> 201", st == 201 and st2 == 201, (st, A, st2, B))
st, b = pedir("POST", "/api/productos", {"nombre": "Malo", "precio": -1}, token=ADMIN)
comprobar("precio negativo -> 400", st == 400, (st, b))
st, b = pedir("GET", "/api/productos?q=lenovo")
comprobar("búsqueda ?q=lenovo", st == 200 and len(b) == 1, b)
st, b = pedir("GET", "/api/productos/abc")
comprobar("id inválido -> 404", st == 404, (st, b))

print("== Pedidos con varios productos (Spring Boot + PostgreSQL)")
st, p1 = pedir("POST", "/api/pedidos", {"usuarioId": admin_id, "items": [
    {"productoId": A["id"], "cantidad": 2}, {"productoId": B["id"], "cantidad": 1}]}, token=CLIENTE)
comprobar("el cliente crea un pedido de 2 productos -> 201", st == 201 and len(p1.get("items", [])) == 2, (st, p1))
comprobar("el pedido queda a nombre del cliente (se ignora usuarioId del cuerpo)", p1.get("usuarioId") == cliente_id, p1)
comprobar("total = 2 x 10.25 + 1 x 3 = 23.50 y estado PENDIENTE", float(p1.get("total", 0)) == 23.5 and p1.get("estado") == "PENDIENTE", p1)
comprobar("stock reservado en MongoDB (A 5->3, B 2->1)", stock(A["id"]) == 3 and stock(B["id"]) == 1, (stock(A["id"]), stock(B["id"])))
st, b = pedir("POST", "/api/pedidos", {"items": [{"productoId": A["id"], "cantidad": 1}, {"productoId": A["id"], "cantidad": 1}]}, token=CLIENTE)
comprobar("productos repetidos se suman en una sola línea", st == 201 and len(b["items"]) == 1 and b["items"][0]["cantidad"] == 2, (st, b))
p_repetido = b
comprobar("stock de A 3->1", stock(A["id"]) == 1, stock(A["id"]))

st, b = pedir("POST", "/api/pedidos", {"items": [{"productoId": A["id"], "cantidad": 1}, {"productoId": B["id"], "cantidad": 5}]}, token=CLIENTE)
comprobar("2.º producto sin stock -> 409 con mensaje de Node", st == 409 and "Stock insuficiente" in detalle(b), (st, b))
comprobar("COMPENSACIÓN: el stock de A que ya se había reservado vuelve (A sigue en 1)", stock(A["id"]) == 1, stock(A["id"]))
st, b = pedir("POST", "/api/pedidos", {"items": []}, token=CLIENTE)
comprobar("pedido sin productos -> 400", st == 400, (st, b))
st, b = pedir("POST", "/api/pedidos", {"items": [{"productoId": A["id"], "cantidad": 0}]}, token=CLIENTE)
comprobar("cantidad 0 -> 400", st == 400, (st, b))
st, b = pedir("POST", "/api/pedidos", {"items": [{"productoId": "aaaaaaaaaaaaaaaaaaaaaaaa", "cantidad": 1}]}, token=CLIENTE)
comprobar("producto inexistente -> 400", st == 400, (st, b))
st, b = pedir("POST", "/api/pedidos", {"items": [{"productoId": B["id"], "cantidad": 1}]}, token=ADMIN)
comprobar("el admin sin usuarioId -> 400", st == 400, (st, b))
st, b = pedir("POST", "/api/pedidos", {"usuarioId": 999999, "items": [{"productoId": B["id"], "cantidad": 1}]}, token=ADMIN)
comprobar("el admin con usuario inexistente -> 400", st == 400 and "no existe" in detalle(b), (st, b))
st, p_admin = pedir("POST", "/api/pedidos", {"usuarioId": nuevo["id"], "items": [{"productoId": B["id"], "cantidad": 1}]}, token=ADMIN)
comprobar("el admin crea un pedido para otro usuario -> 201", st == 201 and p_admin.get("usuarioId") == nuevo["id"], (st, p_admin))

st, mios = pedir("GET", "/api/pedidos", token=CLIENTE)
comprobar("el cliente solo ve sus pedidos", st == 200 and {p["usuarioId"] for p in mios} == {cliente_id}, (st, mios))
st, b = pedir("GET", f"/api/pedidos/{p_admin['id']}", token=CLIENTE)
comprobar("el cliente no ve el pedido de otro -> 404", st == 404, (st, b))
st, todos = pedir("GET", "/api/pedidos", token=ADMIN)
comprobar("el admin ve todos los pedidos", st == 200 and {cliente_id, nuevo["id"]} <= {p["usuarioId"] for p in todos}, st)

print("== Estados y cancelación")
st, b = pedir("PATCH", f"/api/pedidos/{p1['id']}/estado", {"estado": "ENVIADO"}, token=CLIENTE)
comprobar("el cliente no puede marcar ENVIADO -> 403", st == 403, (st, b))
st, b = pedir("PATCH", f"/api/pedidos/{p1['id']}/estado", {"estado": "CANCELADO"}, token=CLIENTE)
comprobar("el cliente cancela su pedido PENDIENTE", st == 200 and b.get("estado") == "CANCELADO", (st, b))
comprobar("al cancelar vuelve el stock de los 2 productos (A 1->3, B 0->1)", stock(A["id"]) == 3 and stock(B["id"]) == 1, (stock(A["id"]), stock(B["id"])))
st, b = pedir("PATCH", f"/api/pedidos/{p1['id']}/estado", {"estado": "CANCELADO"}, token=ADMIN)
comprobar("cancelar dos veces -> 409 y el stock no se devuelve dos veces", st == 409 and stock(A["id"]) == 3, (st, b, stock(A["id"])))
st, b = pedir("PATCH", f"/api/pedidos/{p_repetido['id']}/estado", {"estado": "ENVIADO"}, token=ADMIN)
comprobar("el admin marca ENVIADO", st == 200 and b.get("estado") == "ENVIADO", (st, b))
st, b = pedir("PATCH", f"/api/pedidos/{p_repetido['id']}/estado", {"estado": "CANCELADO"}, token=CLIENTE)
comprobar("el cliente no puede cancelar un pedido ya ENVIADO -> 403", st == 403, (st, b))
st, b = pedir("PATCH", f"/api/pedidos/{p_repetido['id']}/estado", {"estado": "VOLANDO"}, token=ADMIN)
comprobar("estado inválido -> 400", st == 400, (st, b))
st, b = pedir("PATCH", f"/api/pedidos/{p_repetido['id']}/estado", {"estado": "RECHAZADO"}, token=ADMIN)
comprobar("estado interno RECHAZADO no se puede asignar -> 400", st == 400, (st, b))

print("== Concurrencia: 8 pedidos simultáneos de 1 unidad con stock 5")
st, C = pedir("POST", "/api/productos", {"nombre": f"Prueba C {SUFIJO}", "precio": 1, "stock": 5}, token=ADMIN)
with ThreadPoolExecutor(max_workers=8) as ex:
    res = list(ex.map(lambda _: pedir("POST", "/api/pedidos", {"items": [{"productoId": C["id"], "cantidad": 1}]}, token=CLIENTE), range(8)))
codigos = sorted(c for c, _ in res)
comprobar(f"exactamente 5 aceptados y 3 rechazados {codigos}", codigos.count(201) == 5 and codigos.count(409) == 3, codigos)
comprobar("el stock termina en 0 (nunca negativo)", stock(C["id"]) == 0, stock(C["id"]))

print("== Actividad (Go + MongoDB)")
time.sleep(1.5)  # los eventos se envían en segundo plano
st, eventos = pedir("GET", "/api/eventos?limite=300", token=ADMIN)
tipos = {e["tipo"] for e in eventos}
servicios = {e["servicio"] for e in eventos}
comprobar("hay eventos de usuarios, productos y pedidos", {"usuarios", "productos", "pedidos"} <= servicios, servicios)
for t in ["SESION_INICIADA", "USUARIO_REGISTRADO", "USUARIO_CREADO", "PRODUCTO_CREADO", "PEDIDO_CREADO", "PEDIDO_ENVIADO", "PEDIDO_CANCELADO"]:
    comprobar(f"evento {t}", t in tipos, tipos)
st, resumen = pedir("GET", "/api/eventos/resumen", token=ADMIN)
comprobar(f"resumen: {resumen.get('total')} eventos", st == 200 and resumen.get("total", 0) > 0, resumen)

print("== Límite de intentos en el gateway (va al final: agota el cupo de esta IP durante un minuto)")
probando_limite = True
codigos = []
while len(codigos) < 30 and 429 not in codigos:
    st, b = pedir("POST", "/api/auth/login", {"email": f"fuerza{SUFIJO}@gmail.com", "password": "adivinando"})
    codigos.append(st)
comprobar(f"tras {codigos.count(401)} intentos fallidos el gateway responde 429", codigos[-1] == 429 and set(codigos[:-1]) == {401}, codigos)
comprobar("el 429 trae un mensaje en JSON", "Demasiados intentos" in detalle(b), b)

print("== Limpieza")
st, pedidos = pedir("GET", "/api/pedidos", token=ADMIN)
creados = [p for p in pedidos if p["usuarioId"] in (cliente_id, nuevo["id"])]
borrados = [pedir("DELETE", f"/api/pedidos/{p['id']}", token=ADMIN)[0] for p in creados]
comprobar(f"eliminar {len(creados)} pedidos de prueba -> 204", set(borrados) <= {204}, borrados)
comprobar("al eliminar pedidos PENDIENTES su stock vuelve (C 0->5)", stock(C["id"]) == 5, stock(C["id"]))
for producto in (A, B, C):
    pedir("DELETE", f"/api/productos/{producto['id']}", token=ADMIN)
st1, _ = pedir("DELETE", f"/api/usuarios/{cliente_id}", token=ADMIN)
st2, _ = pedir("DELETE", f"/api/usuarios/{nuevo['id']}", token=ADMIN)
st3, _ = pedir("GET", f"/api/productos/{A['id']}")
comprobar("usuarios y productos de prueba eliminados", st1 == 204 and st2 == 204 and st3 == 404, (st1, st2, st3))
st, b = pedir("GET", "/api/pedidos", token=CLIENTE)
comprobar("el token de una cuenta eliminada deja de valer al instante -> 401", st == 401, (st, b))

print(f"\nRESULTADO: {total - fallos}/{total} comprobaciones correctas" + ("" if fallos == 0 else f" — {fallos} FALLAS"))
sys.exit(1 if fallos else 0)
