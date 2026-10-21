# Tienda UJAP — Sistema de pedidos con microservicios

Proyecto Final · **LPR07304 Lenguajes de Programación** · Universidad José Antonio Páez

> **Estado del repositorio: parte 1 de 6.** Aquí está la base de la arquitectura: la infraestructura y las bases de datos. Las demás partes se publicarán en el orden de la tabla de más abajo.

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
| 1 | **Infraestructura base** | `docker-compose.yml` con PostgreSQL y MongoDB, API Gateway (Nginx), variables de entorno y nombre local `tienda.ujap.test` | ✅ Publicada |
| 2 | Servicio de usuarios y autenticación | `servicio-usuarios/` — Python · FastAPI · PostgreSQL | ⏳ Pendiente |
| 3 | Servicio de productos | `servicio-productos/` — Node.js · Express · MongoDB | ⏳ Pendiente |
| 4 | Servicio de actividad | `servicio-actividad/` — Go · MongoDB | ⏳ Pendiente |
| 5 | Servicio de pedidos | `servicio-pedidos/` — Java · Spring Boot · PostgreSQL | ⏳ Pendiente |
| 6 | Frontend, pruebas y documentación | `frontend/`, `tests/`, capturas de pantalla y README completo | ⏳ Pendiente |

## Contenido de la parte 1

```
.
├── docker-compose.yml        ← PostgreSQL, MongoDB y API Gateway
├── .env.example              ← plantilla de variables de entorno
├── .gitignore
├── .gitattributes
├── configurar-dominio.ps1    ← agrega tienda.ujap.test al archivo hosts (Windows)
└── gateway/
    ├── Dockerfile
    └── nginx.conf            ← rutas hacia cada microservicio
```

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

## Cómo probar la parte 1

**Requisito:** Docker Desktop (o Docker Engine + Compose v2).

```bash
git clone <url-del-repositorio>
cd <carpeta-del-repositorio>
cp .env.example .env            # en Windows: copy .env.example .env
docker compose up -d --build
docker compose ps
```

Resultado esperado: `postgres` y `mongodb` en estado `healthy`, y `gateway` en `running`.

Para comprobar las bases de datos:

```bash
docker compose exec postgres sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "select version();"'
docker compose exec mongodb mongosh --quiet --eval "db.adminCommand('ping')"
```

> Como todavía no existen los microservicios ni el frontend, el gateway responde `502 Bad Gateway` a cualquier ruta. Es lo esperado en esta parte.

Para detener todo:

```bash
docker compose down        # conserva los datos
docker compose down -v     # también borra los datos
```

Si el puerto 80 de tu equipo está ocupado, cambia `GATEWAY_PORT` en `.env` (por ejemplo, `8080`).

### Nombre local `tienda.ujap.test`

Para abrir el sistema como `http://tienda.ujap.test` hay que agregar el nombre al archivo `hosts` una sola vez:

- **Windows:** clic derecho en `configurar-dominio.ps1` → *Ejecutar con PowerShell* (pide permiso de administrador).
- **Linux / macOS:** `echo "127.0.0.1 tienda.ujap.test" | sudo tee -a /etc/hosts`

## Variables de entorno

Las credenciales **no están en el código**: se definen en `.env` (excluido de Git por `.gitignore`) y Docker Compose las pasa a cada contenedor. `.env.example` sirve de plantilla; **cambia los valores antes de usarlo fuera de tu equipo**.

| Variable | Uso | Parte |
|---|---|:-:|
| `DB_USER`, `DB_PASS`, `DB_NAME` | PostgreSQL | 1 |
| `MONGO_USER`, `MONGO_PASS`, `MONGO_DB` | MongoDB | 1 |
| `GATEWAY_PORT` | Puerto del gateway en tu máquina (por defecto `80`) | 1 |
| `JWT_SECRET`, `JWT_EXPIRA_MIN` | Firma y duración de los tokens de sesión | 2–5 |
| `ADMIN_EMAIL`, `ADMIN_PASSWORD` | Cuenta de administrador que se crea al primer inicio | 2 |

Para generar un `JWT_SECRET` aleatorio:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

## Decisiones técnicas de la infraestructura

- **Solo el gateway publica un puerto.** Las bases de datos y, más adelante, los microservicios no son accesibles desde fuera de Docker.
- **Dos redes de Docker:** `backend` (bases de datos y microservicios) y `frontend` (gateway, frontend y microservicios). El gateway no puede llegar a las bases de datos.
- **Healthchecks:** los servicios que dependan de una base de datos esperarán a que esté `healthy` antes de arrancar (`depends_on: condition: service_healthy`).
- **Volúmenes** `pgdata` y `mongodata`: los datos persisten entre reinicios.
- **Un solo origen para el navegador:** el frontend solo habla con el gateway, así que no hay problemas de CORS ni de puertos distintos.
