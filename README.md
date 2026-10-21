# Tienda UJAP — Sistema de pedidos con microservicios

Proyecto Final · **LPR07304 Lenguajes de Programación** · Universidad José Antonio Páez

> **Estado del repositorio: parte 4 de 6.** Están publicadas la infraestructura base y los servicios de usuarios, productos y actividad. Las demás partes se publicarán en el orden de la tabla de más abajo.

## ¿Qué hace el sistema?

**Tienda UJAP** es una tienda en línea de productos de computación y tecnología:

- **Los clientes** crean su cuenta, consultan el catálogo, arman pedidos con uno o varios productos y siguen su estado.
- **El administrador** gestiona usuarios y catálogo, ve todos los pedidos y consulta un historial de actividad.

Cada parte del sistema es un **microservicio escrito en un lenguaje distinto**, con su propio contenedor Docker. Cuando estén publicadas todas las partes, todo se levantará con **un solo comando**.

## Arquitectura

```
                                     Navegador
                                         │
                                         ▼  http://tienda.ujap.test
                          ┌──────────────────────────────┐
                          │     API Gateway (Nginx)      │   ← único puerto publicado (80)
                          └──────────────────────────────┘
          │                 │                 │                 │                 │
          ▼ /               ▼ /api/usuarios   ▼ /api/pedidos    ▼ /api/productos  ▼ /api/eventos
   ┌────────────┐   ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐
   │  frontend  │   │   usuarios   │  │   pedidos    │  │  productos   │  │  actividad   │
   │ HTML / JS  │   │Python FastAPI│  │ Java Spring  │  │ Node Express │  │      Go      │
   │  (Nginx)   │   │ + login/JWT  │  │              │  │              │  │              │
   └────────────┘   └──────┬───────┘  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘
                           │                 │                 │                 │
                           └────────┬────────┘                 └────────┬────────┘
                                    ▼                                   ▼
                             ┌────────────┐                      ┌────────────┐
                             │ PostgreSQL │                      │  MongoDB   │
                             │   (SQL)    │                      │  (NoSQL)   │
                             └────────────┘                      └────────────┘
```

Cuatro microservicios, **dos por cada base de datos**:

| Base de datos | Microservicio | Lenguaje / Framework |
|---|---|---|
| PostgreSQL 16 | `servicio-usuarios` — usuarios y login con JWT | Python 3.12 + FastAPI + SQLAlchemy |
| PostgreSQL 16 | `servicio-pedidos` — pedidos con varios productos | Java 21 + Spring Boot + Spring Data JPA |
| MongoDB 7 | `servicio-productos` — catálogo y stock | Node.js 22 + Express 5 + Mongoose |
| MongoDB 7 | `servicio-actividad` — historial de eventos | Go 1.25 + net/http + mongo-driver |

## Las 6 partes del repositorio

El repositorio se publica por partes, ordenadas según sus dependencias: el servicio de pedidos usa a los otros tres, por eso va después de ellos.

| # | Parte | Contenido | Estado |
|:-:|---|---|:-:|
| 1 | Infraestructura base | `docker-compose.yml` con PostgreSQL y MongoDB, API Gateway (Nginx), variables de entorno y nombre local `tienda.ujap.test` | ✅ Publicada |
| 2 | Servicio de usuarios y autenticación | `servicio-usuarios/` — Python · FastAPI · PostgreSQL: registro, login, roles y tokens JWT | ✅ Publicada |
| 3 | Servicio de productos | `servicio-productos/` — Node.js · Express · MongoDB: catálogo y stock | ✅ Publicada |
| 4 | **Servicio de actividad** | `servicio-actividad/` — Go · MongoDB: historial de eventos del sistema | ✅ Publicada |
| 5 | Servicio de pedidos | `servicio-pedidos/` — Java · Spring Boot · PostgreSQL | ⏳ Pendiente |
| 6 | Frontend, pruebas y documentación | `frontend/`, `tests/`, capturas de pantalla y README completo | ⏳ Pendiente |

## Contenido publicado

```
.
├── docker-compose.yml        ← bases de datos, servicios de usuarios, productos y actividad, y API Gateway
├── .env.example              ← plantilla de variables de entorno
├── .gitignore
├── .gitattributes
├── configurar-dominio.ps1    ← agrega tienda.ujap.test al archivo hosts (Windows)
├── gateway/
│   ├── Dockerfile
│   └── nginx.conf            ← rutas hacia cada microservicio
├── servicio-usuarios/        ← parte 2
│   ├── Dockerfile
│   ├── requirements.txt
│   └── app/
│       ├── main.py           ← rutas de autenticación y de usuarios
│       ├── seguridad.py      ← bcrypt, tokens JWT y permisos por rol
│       ├── models.py         ← tabla `usuarios` (SQLAlchemy)
│       ├── schemas.py        ← validación de datos (Pydantic)
│       ├── database.py       ← conexión a PostgreSQL
│       └── actividad.py      ← envío de eventos al servicio de actividad
├── servicio-productos/       ← parte 3
│   ├── Dockerfile
│   ├── package.json / package-lock.json
│   └── src/
│       ├── index.js              ← arranque, conexión a MongoDB y manejo de errores
│       ├── productos.routes.js   ← rutas del catálogo y del stock
│       ├── producto.model.js     ← colección `productos` (Mongoose)
│       ├── auth.js               ← verificación de tokens JWT y permisos por rol
│       ├── actividad.js          ← envío de eventos al servicio de actividad
│       └── seed.js               ← productos de ejemplo
└── servicio-actividad/       ← parte 4
    ├── Dockerfile            ← compilación en dos etapas: la imagen final solo lleva el binario
    ├── go.mod / go.sum
    └── main.go               ← servidor HTTP, verificación de JWT y acceso a MongoDB
```

## Parte 1 — Infraestructura base

### Bases de datos

| Servicio | Imagen | Datos | Comprobación de estado |
|---|---|---|---|
| `postgres` | `postgres:16-alpine` | volumen `pgdata` | `pg_isready` |
| `mongodb` | `mongo:7` | volumen `mongodata` | `ping` con `mongosh` |

Los datos se conservan entre reinicios gracias a los volúmenes.

### API Gateway

Nginx es el único punto de entrada. El frontend y los microservicios no se publican directamente; el gateway reparte las peticiones por ruta:

| Ruta | Destino |
|---|---|
| `/api/auth/*`, `/api/usuarios/*` | `servicio-usuarios` (puerto interno 8000) |
| `/api/productos/*` | `servicio-productos` (3000) |
| `/api/pedidos/*` | `servicio-pedidos` (8080) |
| `/api/eventos/*` | `servicio-actividad` (8080) |
| `/estado/<servicio>` | endpoint `/health` de cada servicio |
| `/` | frontend |

Los endpoints que solo deben usarse entre microservicios (`/api/productos/{id}/reservar`, `/api/productos/{id}/liberar` y `POST /api/eventos`) están **bloqueados desde fuera** (responden `403`).

El gateway resuelve los nombres de los servicios en cada petición, así que arranca aunque alguno todavía no esté disponible.

## Parte 2 — Servicio de usuarios y autenticación

Microservicio en **Python 3.12 + FastAPI + SQLAlchemy 2** que guarda los usuarios en **PostgreSQL**. Cumple dos funciones: administrar usuarios y **autenticar** (inicio de sesión y emisión de tokens).

- Las contraseñas se guardan cifradas con **bcrypt**; nunca en texto plano. Un email inexistente y una contraseña incorrecta devuelven el mismo mensaje.
- Al iniciar sesión se emite un **token JWT** (HS256) que expira a los `JWT_EXPIRA_MIN` minutos (60 por defecto). Los demás microservicios verifican ese token con el mismo `JWT_SECRET`, sin consultar a este servicio en cada petición.
- Hay dos roles: **cliente** y **administrador**. Quien crea su propia cuenta siempre queda como cliente.
- La tabla `usuarios` la crea el propio servicio al arrancar, con reintentos hasta que PostgreSQL esté listo.
- Cada acción importante (inicio de sesión, registro, alta, cambio y baja de usuarios) se envía como evento al servicio de actividad. Si ese servicio no está disponible, deja un aviso en el log y sigue funcionando.

### Permisos

| Acción | Sin sesión | Cliente | Administrador |
|---|:-:|:-:|:-:|
| Crear cuenta e iniciar sesión | ✅ | | |
| Ver y editar sus propios datos | | ✅ | ✅ |
| Ver a cualquier usuario, listar, crear y eliminar usuarios | | | ✅ |
| Cambiar el rol de un usuario | | | ✅ |

### Endpoints

Las rutas marcadas con 🔒 requieren `Authorization: Bearer <token>`. Los errores siempre tienen el formato `{"detail": "mensaje"}`.

| Método | Ruta | Quién | Descripción |
|---|---|---|---|
| POST | `/api/auth/registro` | público | Crear cuenta de cliente → devuelve el token |
| POST | `/api/auth/login` | público | `{email, password}` → `{access_token, usuario}` |
| GET | `/api/auth/yo` | 🔒 | Datos del usuario del token |
| GET | `/api/usuarios` | 🔒 admin | Listar usuarios |
| GET | `/api/usuarios/{id}` | 🔒 admin o el propio usuario | Obtener un usuario |
| POST | `/api/usuarios` | 🔒 admin | Crear usuario (con rol) |
| PUT | `/api/usuarios/{id}` | 🔒 admin o el propio usuario | Actualizar (solo el admin cambia roles) |
| DELETE | `/api/usuarios/{id}` | 🔒 admin | Eliminar (no puede eliminarse a sí mismo) |
| GET | `/health` | público | Estado del servicio (el gateway lo publica como `/estado/usuarios`) |

La contraseña debe tener entre 8 y 72 caracteres. Un email repetido responde `409` y los datos inválidos `422`.

La documentación interactiva (Swagger) está en **`/api/usuarios/docs`**: haz login, copia el `access_token` y pégalo en el botón *Authorize*.

### Cuentas de demostración

La primera vez que arranca el servicio (con la tabla vacía) se crean estos datos de demostración:

| Rol | Email | Contraseña |
|---|---|---|
| Cliente | `maria.perez@gmail.com`, `jose.rodriguez@gmail.com`, `ana.gomez@ujap.edu.ve` | `Cliente2026` |
| Administrador | el de `ADMIN_EMAIL` | el de `ADMIN_PASSWORD` |

El administrador se crea si no existe ninguno, con las variables `ADMIN_EMAIL` y `ADMIN_PASSWORD` de tu `.env`.

## Parte 3 — Servicio de productos

Microservicio en **Node.js 22 + Express 5 + Mongoose 8** que guarda el catálogo en **MongoDB** (colección `productos`).

- **Verifica los tokens JWT** que emite el servicio de usuarios, con el mismo `JWT_SECRET`, sin consultarle nada. El catálogo se puede **leer sin iniciar sesión**; para modificarlo hay que ser administrador.
- La primera vez que arranca, con la colección vacía, carga **6 productos de ejemplo**.
- **Validación:** el precio no puede ser negativo y el stock debe ser un entero mayor o igual que 0 (`400`). Un id con formato inválido responde `404`. La búsqueda `?q=` no distingue mayúsculas y escapa los caracteres especiales.
- Cada alta, cambio y baja de producto se envía como evento al servicio de actividad. Si ese servicio no está disponible, deja un aviso en el log y sigue funcionando.
- Arranca con reintentos hasta que MongoDB esté disponible, y la imagen corre con un usuario sin privilegios (`node`).

### Stock a prueba de fallos

Los endpoints `reservar` y `liberar` son para uso **interno**: solo aceptan un token de *servicio* (el que firmará el servicio de pedidos, parte 5) y el gateway los bloquea desde fuera.

- **Sin sobreventa:** comprobar que hay stock suficiente y descontarlo ocurre en **una sola operación atómica** sobre el documento. Con varias compras simultáneas nunca se vende más de lo que hay.
- **Idempotentes:** cada operación lleva una `referencia` única (por ejemplo, `pedido-12-<producto>`). Si la misma reserva se repite por un reintento o un *timeout*, el stock no se descuenta dos veces.
- **Liberar es seguro:** solo devuelve stock de una reserva que realmente se aplicó, y nunca dos veces.
- Las referencias ya usadas se guardan en un campo interno (`movimientos`) que no aparece en las respuestas de la API.

### Permisos

| Acción | Sin sesión | Cliente | Administrador | Otro microservicio |
|---|:-:|:-:|:-:|:-:|
| Ver el catálogo y buscar | ✅ | ✅ | ✅ | ✅ |
| Crear, modificar y eliminar productos | | | ✅ | |
| Reservar y liberar stock | | | | ✅ |

### Endpoints

| Método | Ruta | Quién | Descripción |
|---|---|---|---|
| GET | `/api/productos?q=&categoria=` | público | Catálogo, con búsqueda por nombre y filtro por categoría |
| GET | `/api/productos/{id}` | público | Un producto |
| POST | `/api/productos` | 🔒 admin | Crear `{nombre, precio, stock, categoria?, descripcion?}` |
| PUT | `/api/productos/{id}` | 🔒 admin | Actualizar |
| DELETE | `/api/productos/{id}` | 🔒 admin | Eliminar |
| POST | `/api/productos/{id}/reservar` | 🔒 servicio (interno) | `{cantidad, referencia}` descuenta stock; `409` si no alcanza |
| POST | `/api/productos/{id}/liberar` | 🔒 servicio (interno) | `{cantidad, referencia}` devuelve stock reservado |
| GET | `/health` | público | Estado del servicio (el gateway lo publica como `/estado/productos`) |

## Parte 4 — Servicio de actividad

Microservicio en **Go 1.25** (solo la biblioteca estándar `net/http` más el driver oficial de MongoDB y una biblioteca de JWT) que guarda en **MongoDB** (colección `eventos`) el historial de todo lo que ocurre en el sistema.

- Los demás microservicios le **envían un evento** por cada acción importante. Cada evento tiene `servicio`, `tipo`, `mensaje`, `datos` opcionales y la `fecha` (que pone el servidor).
- **Solo el administrador puede consultar** el historial; **solo otros microservicios pueden registrar** eventos. Verifica los tokens JWT con el mismo `JWT_SECRET` (`401` si falta o es inválido o expiró, `403` si el rol no corresponde).
- El resumen usa una **agregación de MongoDB** (`$group`) para contar los eventos por microservicio.
- **Dependencia opcional:** si este servicio no está disponible, los demás siguen funcionando; solo se pierde ese registro y dejan un aviso en su log.
- Se compila en **dos etapas**: la imagen final solo contiene el binario y corre con un usuario sin privilegios (`nobody`).
- Reintenta la conexión a MongoDB hasta que esté listo y registra cada petición en el log (salvo `/health`).

Eventos que ya generan las partes publicadas:

| Servicio | Tipos de evento |
|---|---|
| `usuarios` | `SESION_INICIADA`, `USUARIO_REGISTRADO`, `USUARIO_CREADO`, `USUARIO_ACTUALIZADO`, `USUARIO_ELIMINADO` |
| `productos` | `PRODUCTO_CREADO`, `PRODUCTO_ACTUALIZADO`, `PRODUCTO_ELIMINADO` |

### Permisos

| Acción | Sin sesión | Cliente | Administrador | Otro microservicio |
|---|:-:|:-:|:-:|:-:|
| Consultar eventos y resumen | | | ✅ | |
| Registrar un evento | | | | ✅ |

### Endpoints

| Método | Ruta | Quién | Descripción |
|---|---|---|---|
| GET | `/api/eventos?servicio=&limite=` | 🔒 admin | Últimos eventos, del más reciente al más antiguo (`limite` entre 1 y 500, por defecto 50) |
| GET | `/api/eventos/resumen` | 🔒 admin | `{total, por_servicio: [{servicio, total}]}` |
| POST | `/api/eventos` | 🔒 servicio (interno) | `{servicio, tipo, mensaje, datos?}` → `201`; `400` si falta alguno de los tres primeros |
| GET | `/health` | público | Estado del servicio (el gateway lo publica como `/estado/actividad`) |

## Cómo probar lo publicado

**Requisito:** Docker Desktop (o Docker Engine + Compose v2).

```bash
git clone <url-del-repositorio>
cd <carpeta-del-repositorio>
cp .env.example .env            # en Windows: copy .env.example .env
docker compose up -d --build
docker compose ps
```

La primera vez tarda unos minutos (se descargan imágenes y se instalan o compilan las dependencias). Resultado esperado: `postgres`, `mongodb`, `servicio-usuarios`, `servicio-productos` y `servicio-actividad` en estado `healthy`, y `gateway` en `running`.

Probar la autenticación (parte 2) a través del gateway:

```bash
# 1. Iniciar sesión como cliente de demostración → devuelve el access_token
curl -s -X POST http://localhost/api/auth/login -H "Content-Type: application/json" \
     -d '{"email": "maria.perez@gmail.com", "password": "Cliente2026"}'

# 2. Con ese token: tus datos
curl -s http://localhost/api/auth/yo -H "Authorization: Bearer <token>"

# 3. Un cliente no puede listar usuarios → 403
curl -s -i http://localhost/api/usuarios -H "Authorization: Bearer <token>"
```

Probar el catálogo (parte 3):

```bash
# El catálogo es público (no necesita token)
curl -s http://localhost/api/productos
curl -s "http://localhost/api/productos?q=laptop"

# Crear un producto sin token → 401
curl -s -i -X POST http://localhost/api/productos -H "Content-Type: application/json" \
     -d '{"nombre": "Webcam Logitech C920", "precio": 59.9, "stock": 10}'

# Con el token del administrador (inicia sesión con ADMIN_EMAIL y ADMIN_PASSWORD de tu .env) → 201
curl -s -X POST http://localhost/api/productos -H "Authorization: Bearer <token-admin>" \
     -H "Content-Type: application/json" \
     -d '{"nombre": "Webcam Logitech C920", "precio": 59.9, "stock": 10, "categoria": "Accesorios"}'

# Los endpoints internos están bloqueados desde fuera → 403
curl -s -i -X POST http://localhost/api/productos/<id>/reservar
```

Probar el historial de actividad (parte 4). Las acciones anteriores ya generaron eventos:

```bash
# El administrador consulta los últimos eventos y el resumen por servicio
curl -s "http://localhost/api/eventos?limite=5" -H "Authorization: Bearer <token-admin>"
curl -s http://localhost/api/eventos/resumen -H "Authorization: Bearer <token-admin>"

# Solo los eventos de un servicio
curl -s "http://localhost/api/eventos?servicio=productos" -H "Authorization: Bearer <token-admin>"

# Un cliente no puede consultarlo → 403; sin token → 401
curl -s -i http://localhost/api/eventos -H "Authorization: Bearer <token-cliente>"

# Registrar eventos desde fuera está bloqueado en el gateway → 403
curl -s -i -X POST http://localhost/api/eventos
```

Para comprobar las bases de datos:

```bash
docker compose exec postgres sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "select id, nombre, email, rol from usuarios;"'
docker compose exec mongodb sh -c 'mongosh -u "$MONGO_INITDB_ROOT_USERNAME" -p "$MONGO_INITDB_ROOT_PASSWORD" --authenticationDatabase admin --quiet tienda --eval "db.productos.countDocuments(); db.eventos.countDocuments()"'
```

> Como todavía no existen el servicio de pedidos ni el frontend, el gateway responde `502 Bad Gateway` en `/` y en `/api/pedidos`. Es lo esperado en esta etapa.

Para detener todo:

```bash
docker compose down        # conserva los datos
docker compose down -v     # también borra los datos
```

Si el puerto 80 de tu equipo está ocupado, cambia `GATEWAY_PORT` en `.env` (por ejemplo, `8080`) y usa `http://localhost:8080`.

### Nombre local `tienda.ujap.test`

Para abrir el sistema como `http://tienda.ujap.test` hay que agregar el nombre al archivo `hosts` una sola vez:

- **Windows:** clic derecho en `configurar-dominio.ps1` → *Ejecutar con PowerShell* (pide permiso de administrador).
- **Linux / macOS:** `echo "127.0.0.1 tienda.ujap.test" | sudo tee -a /etc/hosts`

## Variables de entorno

Las credenciales **no están en el código**: se definen en `.env` (excluido de Git por `.gitignore`) y Docker Compose las pasa a cada contenedor. `.env.example` sirve de plantilla. Los valores por defecto del código son solo para desarrollo: **cámbialos antes de usar el sistema fuera de tu equipo**.

| Variable | Uso | Parte |
|---|---|:-:|
| `DB_USER`, `DB_PASS`, `DB_NAME` | PostgreSQL | 1 |
| `MONGO_USER`, `MONGO_PASS`, `MONGO_DB` | MongoDB | 1, 3 y 4 |
| `GATEWAY_PORT` | Puerto del gateway en tu máquina (por defecto `80`) | 1 |
| `JWT_SECRET` | Secreto con el que se firman y verifican los tokens (mínimo 32 caracteres) | 2, 3 y 4 |
| `JWT_EXPIRA_MIN` | Duración de la sesión en minutos (por defecto 60) | 2 |
| `ADMIN_EMAIL`, `ADMIN_PASSWORD` | Cuenta de administrador que se crea al primer inicio | 2 |

Para generar un `JWT_SECRET` aleatorio:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

## Decisiones técnicas

- **Solo el gateway publica un puerto.** Las bases de datos y los microservicios no son accesibles desde fuera de Docker.
- **Dos redes de Docker:** `backend` (bases de datos y microservicios) y `frontend` (gateway, frontend y microservicios). El gateway no puede llegar a las bases de datos.
- **Healthchecks:** cada microservicio espera a que su base de datos esté `healthy` antes de arrancar (`depends_on: condition: service_healthy`).
- **Volúmenes** `pgdata` y `mongodata`: los datos persisten entre reinicios.
- **Un solo origen para el navegador:** el frontend solo habla con el gateway, así que no hay problemas de CORS ni de puertos distintos.
- **JWT con secreto compartido:** cada microservicio valida los tokens por su cuenta, sin depender del servicio de usuarios en cada petición.
- **Operaciones de stock atómicas e idempotentes:** el estado se protege en la propia base de datos, no en el código que la llama.
- **Registro de eventos desacoplado:** los servicios envían los eventos sin esperar la respuesta y, si el servicio de actividad falla, lo ignoran; una caída del historial no interrumpe las ventas.
