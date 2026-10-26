# Decisiones de diseño — Tienda UJAP

Este documento explica **por qué** el sistema está construido como está: qué se decidió en cada
punto importante, qué otras opciones había y qué consecuencias tiene la elección. El README explica
**cómo** usarlo.

Cada decisión sigue el mismo formato: **Contexto** (el problema), **Decisión** (lo que se hizo),
**Alternativas** (lo que se descartó y por qué) y **Consecuencias** (lo que se gana y lo que cuesta).

---

## 1. Un microservicio por lenguaje, dos por cada base de datos

**Contexto.** El enunciado pide cuatro microservicios (Express, FastAPI, Spring Boot y Go), una base
de datos SQL y otra NoSQL, con dos microservicios por base de datos, todo levantado con un comando.

**Decisión.** Se repartió el dominio de la tienda según qué datos encaja mejor en cada base:

| Base | Microservicio | Por qué ahí |
|---|---|---|
| PostgreSQL | usuarios (FastAPI) | cuentas con email único y relaciones (códigos, historial de contraseñas) |
| PostgreSQL | pedidos (Spring Boot) | pedidos con sus líneas: datos relacionales con transacciones |
| MongoDB | productos (Express) | catálogo de documentos flexibles; actualizaciones atómicas sobre un documento |
| MongoDB | actividad (Go) | eventos de forma libre (`datos` variable) y agregaciones para el resumen |

**Alternativas.** Poner tres servicios en una base y uno en la otra habría sido más cómodo para
algunas relaciones, pero no cumple el enunciado al pie de la letra.

**Consecuencias.** Cada servicio es dueño de sus tablas o colecciones; ninguno lee los datos de otro
directamente: se comunican por HTTP.

## 2. Un API Gateway como único punto de entrada

**Contexto.** El navegador necesita hablar con cuatro servicios en puertos distintos, y no conviene
exponer los servicios ni las bases de datos.

**Decisión.** Nginx recibe todo el tráfico y lo reparte por ruta (`/api/usuarios`, `/api/productos`,
etc.). Solo el gateway publica puertos (80 y 443), y solo en esta máquina (`127.0.0.1` y `::1`). Hay dos redes de Docker: `backend` (bases de datos
y servicios) y `frontend` (gateway, frontend y servicios), así que el gateway no puede llegar a las
bases de datos.

**Alternativas.** Publicar cada servicio en su puerto obliga a configurar CORS y deja más superficie
de ataque.

**Consecuencias.** El frontend usa rutas relativas (un solo origen, sin CORS). El gateway concentra
las protecciones transversales: HTTPS, límite de intentos, verificación de sesión y bloqueo de
endpoints internos.

## 3. Tokens JWT con un secreto compartido

**Contexto.** Los cuatro servicios necesitan saber quién hace cada petición y con qué rol.

**Decisión.** El servicio de usuarios emite un JWT HS256 (60 minutos) al iniciar sesión. Los otros
tres lo verifican con el mismo `JWT_SECRET` y solo aceptan firmas HMAC con esa clave, así que se
rechazan los tokens sin firma (`alg: none`) o firmados con otro tipo de algoritmo.

**Alternativas.** Sesiones guardadas en el servidor obligarían a cada servicio a consultar una
base compartida. RS256 (clave pública/privada) evitaría compartir el secreto, pero para cuatro servicios
de un mismo equipo la ganancia no compensa la complejidad.

**Consecuencias.** Cada servicio decide los permisos por su cuenta. El punto débil de un JWT puro
(sigue valiendo hasta que expira) se resuelve en la decisión 4.

## 4. Revocación inmediata de sesiones con `auth_request`

**Contexto.** Con JWT puro, cerrar sesión solo borra el token del navegador: quien lo hubiera copiado
podría seguir usándolo hasta que expire. Lo mismo con una cuenta eliminada o a la que se le cambió la
contraseña.

**Decisión.** Antes de pasar cualquier petición a `/api/`, Nginx hace una subpetición
(`auth_request`) a la ruta interna `/interno/verificar` del servicio de usuarios. Ese servicio
comprueba firma, expiración y además:

- **`jti`** (identificador único del token): *Cerrar sesión* lo guarda en `tokens_revocados` hasta que
  el token expira. Así se cierra solo esa sesión.
- **`ver`** (versión de sesión del usuario): cambiar la contraseña o el rol, o que el administrador
  pulse *Cerrar sesiones*, sube la versión y anula **todos** los tokens del usuario de una vez.
- Que el usuario siga existiendo, y que no sea un token de servicio llegado desde fuera de Docker.

**Alternativas.** Que cada servicio consulte la lista de revocados repetiría la misma lógica en
cuatro lenguajes. Tokens de vida muy corta con renovación reducen el problema pero no lo eliminan.

**Consecuencias.** Una consulta rápida por petición con token. Si el servicio de usuarios se cae, las
peticiones **con** token reciben `503` (se prefiere fallar cerrado: no dejar pasar sin comprobar);
las que no llevan token, como ver el catálogo, siguen funcionando. `/interno/verificar` no está bajo
`/api`, así que no se puede llamar desde fuera.

## 5. Tokens de servicio firmados y de corta duración

**Contexto.** Algunas rutas solo deben usarlas otros servicios (reservar stock, registrar eventos).

**Decisión.** El servicio que llama firma un JWT con rol `servicio` que vence a los **5 minutos**.
Además, el gateway bloquea esas rutas desde fuera (`403`) y rechaza cualquier token de servicio que
llegue por él.

**Alternativas.** Una cabecera con una clave fija compartida (`X-Internal-Token`) es más simple, pero
no vence nunca, no identifica quién llama y se suele comparar con `==` (comparación que no es de
tiempo constante).

**Consecuencias.** Dos barreras independientes: la red (gateway) y la firma con vencimiento.

## 6. Stock atómico e idempotente

**Contexto.** Varias personas pueden comprar el último producto a la vez, y una petición repetida por
un reintento no debe descontar stock dos veces.

**Decisión.** Reservar es una sola operación atómica de MongoDB que comprueba y descuenta a la vez
(`stock >= cantidad`), y cada movimiento lleva una referencia única (`pedido-<id>-<producto>`) que se
guarda en el documento: repetirla no tiene efecto. Liberar solo devuelve lo que realmente se reservó.

**Alternativas.** Leer el stock, comprobarlo en el código y luego escribirlo tiene una condición de
carrera: dos compras simultáneas pueden pasar la comprobación.

**Consecuencias.** La prueba de 8 compras simultáneas con stock 5 termina siempre en 5 aceptadas,
3 rechazadas y stock 0.

## 7. Pedidos tolerantes a fallos (compensación y recuperación)

**Contexto.** Crear un pedido toca tres servicios. Cualquiera puede fallar a mitad de camino.

**Decisión.** El pedido se guarda primero como `PROCESANDO`; luego se reserva el stock producto por
producto. Si uno falla, se libera lo ya reservado y el pedido se descarta (**compensación**). Si el
propio servicio de pedidos se cae a mitad, una tarea cada 30 s busca pedidos `PROCESANDO` de más de
60 s, devuelve su stock y los marca `RECHAZADO` (**recuperación**).

**Alternativas.** Una transacción distribuida (2PC) no es posible entre PostgreSQL, MongoDB y HTTP.

**Consecuencias.** Nunca queda stock descontado sin pedido. Es el patrón *saga* en su forma más simple.

## 8. Servicios auxiliares que no detienen la venta

**Contexto.** El historial de actividad y el correo son útiles, pero no imprescindibles para vender.

**Decisión.** Los eventos y los correos se envían en segundo plano. Si fallan, se deja constancia en
el log y la operación principal sigue.

**Consecuencias.** Una caída del servicio de actividad o del servidor de correo no interrumpe ventas.
Se acepta perder ese evento o ese aviso.

## 9. Confirmación del correo con un código de un solo uso

**Contexto.** Sin confirmar el correo, cualquiera podría registrarse con una dirección ajena.

**Decisión.** Registrarse crea la cuenta **sin confirmar** y envía un código de 6 dígitos:

- Se genera con `secrets` (apto para seguridad) y **no se guarda**: en la base solo hay un HMAC del
  código mezclado con el usuario y el propósito (un código no sirve para otra cuenta ni para otra cosa).
- Vence a los **15 minutos**, sirve **una vez** y se anula tras **5 intentos fallidos**.
- Reenviar el código responde lo mismo exista o no la cuenta (no revela qué correos están registrados).
- Un registro sin confirmar se puede repetir: así nadie bloquea un correo ajeno registrándolo antes.
- Se rechazan dominios que no existen o no tienen registros MX ni A; si el DNS no responde (sin
  Internet), se acepta y el código queda como comprobación definitiva.
- Un cliente que cambia su correo debe confirmar el nuevo.

**Alternativas.** Un enlace con token en el correo es más cómodo, pero obliga a conocer la URL
pública del sitio; el código funciona igual en cualquier dirección.

**Consecuencias.** Las cuentas que crea el administrador y las de ejemplo nacen confirmadas. Las ya
existentes se marcaron como confirmadas al migrar.

## 10. Recuperación e historial de contraseñas

**Contexto.** Hacía falta una forma segura de recuperar el acceso sin que el administrador conozca
la contraseña.

**Decisión.** *¿Olvidaste tu contraseña?* envía un código (mismas reglas que la decisión 9). Con él se
elige una contraseña nueva, que no puede ser la actual ni ninguna de las **3 anteriores** (se comparan
con sus hashes bcrypt). Todo cambio de contraseña cierra todas las sesiones y envía un correo de aviso
a la dirección de la cuenta.

**Consecuencias.** Si la contraseña nueva se rechaza, no se confirma nada en la base y el código sigue
sirviendo para otro intento.

## 11. Límite de intentos en el gateway, con cupos separados

**Contexto.** Sin límite, se pueden probar contraseñas o códigos sin parar, o usar el sistema para
llenar de correos el buzón de otra persona.

**Decisión.** Nginx limita por dirección IP (`limit_req`) y responde `429` en JSON con `Retry-After`:

| Cupo | Rutas | Límite |
|---|---|---|
| `acceso` | login y registro | 10 por minuto + ráfaga de 10 |
| `codigos` | confirmar correo y restablecer contraseña | 10 por minuto + ráfaga de 20 |
| `correos` | reenviar código y recuperar contraseña | 5 por minuto + ráfaga de 5 |

**Alternativas.** Limitar dentro de cada servicio repetiría la lógica y no protegería a los demás.

**Consecuencias.** Son riesgos distintos, por eso tienen cupos distintos: adivinar códigos ya es inútil
por el límite de 5 intentos, así que ese cupo es más generoso. Las pruebas automáticas comprueban el
límite al final y piden esperar un minuto si se ejecutan dos veces seguidas.

## 12. HTTPS con una autoridad certificadora local restringida

**Contexto.** Sin HTTPS, las contraseñas y los tokens viajan en texto plano. En desarrollo no hay un
certificado público para `tienda.ujap.test` (`.test` es un dominio reservado).

**Decisión.** Al arrancar por primera vez, el gateway crea una **CA local** y un certificado para el
sitio firmado por ella (como hace la herramienta `mkcert`):

- La CA solo puede firmar `tienda.ujap.test`, `localhost` y `127.0.0.1` (*name constraints*), y su
  **clave privada se borra** después de firmar. Importarla en Windows (`configurar-dominio.ps1`) quita
  la advertencia del navegador sin abrir un riesgo: no sirve para falsificar ningún otro sitio.
- TLS 1.2 y 1.3, HTTP/2. HTTP redirige con `308` (conserva el método, así un `POST` sigue siendo `POST`).
- **No** se envía HSTS a propósito: con un certificado que el navegador aún no conoce, HSTS impediría
  entrar aceptando la advertencia.

**Alternativas.** Un certificado autofirmado suelto siempre muestra la advertencia y, si se importa
como raíz de confianza, no tiene restricciones de nombre.

**Consecuencias.** Las pruebas automáticas verifican el certificado de verdad (confiando solo en esa
CA), no lo ignoran.

## 13. Correo con Mailpit en desarrollo y SMTP configurable

**Contexto.** Hay que enviar correos sin depender de una cuenta real durante el desarrollo.

**Decisión.** Mailpit recibe todos los correos y los muestra en `http://mailpit.correo`, un nombre que
atiende el gateway (y también en `http://localhost:8025`). Como el gateway solo escucha en esta máquina,
otros equipos de la red no pueden leerlos; por eso, abrir el gateway a la red (`GATEWAY_IP=0.0.0.0`)
expone también el buzón. Guarda los correos en un volumen, así que sobreviven a los reinicios. Con las variables `SMTP_*` los
mismos servicios envían por un servidor real (por ejemplo, Gmail con contraseña de aplicación).

**Consecuencias.** Las pruebas leen los códigos desde la API de Mailpit, igual que una persona los
leería en su buzón.

## 14. Avisos de pedidos desde el servicio de Java

**Contexto.** El cliente debe enterarse cuando se crea su pedido o cambia de estado.

**Decisión.** El servicio de pedidos envía el aviso (Spring Mail), porque es el dueño del ciclo de vida
del pedido. El correo del cliente se consulta al servicio de usuarios en el momento de enviar.

**Alternativas.** Guardar el correo en el pedido duplicaría un dato que puede cambiar.

**Consecuencias.** El aviso llega a la dirección actual del cliente, también cuando el pedido lo crea el
administrador.

## 15. Cambios de esquema al arrancar

**Contexto.** Las funciones nuevas agregaron columnas a la tabla `usuarios`, que ya existía en los
volúmenes de quienes usaban versiones anteriores.

**Decisión.** Al arrancar, el servicio de usuarios ejecuta `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`
para cada columna nueva (las tablas nuevas las crea SQLAlchemy). En el servicio de Java, Hibernate
actualiza el esquema (`ddl-auto=update`).

**Alternativas.** Una herramienta de migraciones (Alembic, Flyway) es lo indicado cuando el esquema
cambia a menudo; para pocos cambios aditivos sería más configuración que beneficio.

**Consecuencias.** Actualizar no exige borrar los datos (`docker compose down -v`).

## 16. Pruebas de extremo a extremo a través del gateway

**Contexto.** Lo que importa es que el sistema completo funcione como lo usa el navegador.

**Decisión.** `tests/e2e.py` (solo biblioteca estándar de Python) recorre todo por HTTPS a través del
gateway: 115 comprobaciones de permisos, revocación, correo, recuperación, pedidos, compensación,
concurrencia, eventos y límites. Al terminar borra los datos que creó.

**Consecuencias.** No requiere instalar nada y prueba las piezas juntas, que es donde suelen aparecer
los errores de un sistema de microservicios.
