// Frontend de la Tienda UJAP.
// Todas las peticiones van al API Gateway (mismo origen), que las reparte a cada microservicio.
// La sesión es un token JWT emitido por el servicio de usuarios; se envía en cada petición.

const SERVICIOS = [
  { id: 'usuarios', nombre: 'Usuarios', tecnologia: 'FastAPI' },
  { id: 'productos', nombre: 'Productos', tecnologia: 'Express' },
  { id: 'pedidos', nombre: 'Pedidos', tecnologia: 'Spring Boot' },
  { id: 'actividad', nombre: 'Actividad', tecnologia: 'Go' },
];
const VISTAS_POR_ROL = {
  admin: ['usuarios', 'productos', 'pedidos', 'actividad'],
  cliente: ['productos', 'pedidos'],
};
const ESTADOS_ELEGIBLES = ['PENDIENTE', 'ENVIADO', 'ENTREGADO', 'CANCELADO'];
const ESTADOS_FINALES = ['CANCELADO', 'RECHAZADO', 'PROCESANDO'];

const moneda = new Intl.NumberFormat('es-VE', { style: 'currency', currency: 'USD' });
const fechaHora = new Intl.DateTimeFormat('es-VE', { dateStyle: 'short', timeStyle: 'medium' });

const $ = (selector) => document.querySelector(selector);

let sesion = leerSesion();
let usuarios = [];
let productos = [];
let carrito = [];
let vistaActual = null;

// ───────────── Utilidades ─────────────

function esc(valor) {
  const reemplazos = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' };
  return String(valor ?? '').replace(/[&<>"']/g, (c) => reemplazos[c]);
}

function leerSesion() {
  try {
    return JSON.parse(sessionStorage.getItem('sesion')) || null;
  } catch {
    return null;
  }
}

function guardarSesion(datos) {
  sesion = datos;
  try {
    if (datos) sessionStorage.setItem('sesion', JSON.stringify(datos));
    else sessionStorage.removeItem('sesion');
  } catch {
    // sin almacenamiento disponible: la sesión dura mientras la página esté abierta
  }
}

const esAdmin = () => sesion?.usuario.rol === 'admin';

async function api(ruta, { metodo = 'GET', cuerpo } = {}) {
  const opciones = { method: metodo, headers: {} };
  if (sesion) opciones.headers.Authorization = `Bearer ${sesion.token}`;
  if (cuerpo !== undefined) {
    opciones.headers['Content-Type'] = 'application/json';
    opciones.body = JSON.stringify(cuerpo);
  }
  const respuesta = await fetch(ruta, opciones);
  if (respuesta.status === 204) return null;
  const datos = await respuesta.json().catch(() => null);
  // El gateway responde 401 si el token expiró o si la sesión se cerró (en este u otro dispositivo)
  if (respuesta.status === 401 && sesion && !ruta.startsWith('/api/auth/')) {
    cerrarSesion(mensajeDeError(datos, 401));
    throw new Error('Sesión expirada');
  }
  if (!respuesta.ok) {
    const error = new Error(mensajeDeError(datos, respuesta.status));
    error.status = respuesta.status;
    throw error;
  }
  return datos;
}

// Todos los servicios responden errores como {"detail": "..."}; FastAPI usa una lista en validaciones
function mensajeDeError(datos, status) {
  const detalle = datos?.detail;
  if (Array.isArray(detalle)) return detalle.map((e) => `${e.loc?.at(-1) ?? ''}: ${e.msg}`).join(' · ');
  if (typeof detalle === 'string') return detalle;
  if ([502, 503, 504].includes(status)) return 'El microservicio no está disponible en este momento';
  return `Error ${status}`;
}

let temporizadorAviso;
function avisar(texto, tipo = 'ok') {
  const aviso = $('#aviso');
  aviso.textContent = texto;
  aviso.className = `aviso visible ${tipo}`;
  clearTimeout(temporizadorAviso);
  temporizadorAviso = setTimeout(() => aviso.classList.remove('visible'), 4000);
}

// Cuadro de confirmación propio. Devuelve una promesa: true si se acepta, false si se cancela
// (botón, tecla Escape o clic fuera del cuadro). Reemplaza al confirm() del navegador.
function confirmar({ titulo, mensaje, aceptar = 'Aceptar', cancelar = 'Volver', peligro = false }) {
  return new Promise((resolver) => {
    const modal = $('#modal');
    const botonAceptar = $('#modal-aceptar');
    const botonCancelar = $('#modal-cancelar');
    const previo = document.activeElement;

    $('#modal-titulo').textContent = titulo;
    $('#modal-mensaje').textContent = mensaje;
    $('#modal-icono').textContent = peligro ? '!' : '?';
    botonAceptar.textContent = aceptar;
    botonCancelar.textContent = cancelar;
    modal.classList.toggle('modal-peligro', peligro);

    const cerrar = (resultado) => {
      modal.hidden = true;
      document.removeEventListener('keydown', alTeclear);
      modal.removeEventListener('mousedown', alHacerClic);
      botonAceptar.onclick = botonCancelar.onclick = null;
      previo?.focus?.();
      resolver(resultado);
    };
    // Escape cancela; Tab se queda dentro del cuadro
    const alTeclear = (e) => {
      if (e.key === 'Escape') return cerrar(false);
      if (e.key !== 'Tab') return;
      const [primero, ultimo] = [botonCancelar, botonAceptar];
      if (e.shiftKey && document.activeElement === primero) { e.preventDefault(); ultimo.focus(); }
      else if (!e.shiftKey && document.activeElement === ultimo) { e.preventDefault(); primero.focus(); }
    };
    const alHacerClic = (e) => { if (e.target === modal) cerrar(false); };

    botonAceptar.onclick = () => cerrar(true);
    botonCancelar.onclick = () => cerrar(false);
    document.addEventListener('keydown', alTeclear);
    modal.addEventListener('mousedown', alHacerClic);
    modal.hidden = false;
    botonCancelar.focus(); // en acciones destructivas, el foco empieza en la opción segura
  });
}

function filaVacia(columnas, texto, esError = false) {
  return `<tr><td colspan="${columnas}" class="vacio ${esError ? 'error-carga' : ''}">${esc(texto)}</td></tr>`;
}

// Lee un formulario y descarta los campos vacíos
function leerFormulario(form) {
  const datos = {};
  for (const [clave, valor] of new FormData(form)) {
    const texto = String(valor).trim();
    if (texto !== '') datos[clave] = texto;
  }
  return datos;
}

// Envía un formulario deshabilitando el botón mientras espera la respuesta
function alEnviar(form, accion) {
  form.addEventListener('submit', async (evento) => {
    evento.preventDefault();
    const boton = form.querySelector('button[type="submit"]');
    boton.disabled = true;
    try {
      await accion(leerFormulario(form));
    } catch (error) {
      if (error.message !== 'Sesión expirada') avisar(error.message, 'error');
    } finally {
      boton.disabled = false;
    }
  });
}

// ───────────── Sesión ─────────────

const FORMULARIOS_ACCESO = ['login', 'registro', 'verificar'];

function mostrarAcceso(formulario) {
  document.querySelectorAll('.acceso-pestana').forEach((b) => b.classList.toggle('activa', b.dataset.acceso === formulario));
  for (const f of FORMULARIOS_ACCESO) $(`#form-${f}`).hidden = f !== formulario;
}

// Muestra el formulario para escribir el código que llegó por correo
function pedirCodigo(email) {
  const form = $('#form-verificar');
  form.reset();
  form.elements.email.value = email;
  $('#verificar-email').textContent = email;
  mostrarAcceso('verificar');
  form.elements.codigo.focus();
}

// Buzón de pruebas Mailpit: solo se publica en esta máquina (puerto 8025)
document.querySelectorAll('.enlace-buzon').forEach((a) => { a.href = `http://${location.hostname}:8025`; });

function iniciarSesion(respuesta) {
  guardarSesion({ token: respuesta.access_token, usuario: respuesta.usuario });
  avisar(`Hola, ${respuesta.usuario.nombre}`);
  mostrarApp();
}

function cerrarSesion(mensaje) {
  guardarSesion(null);
  carrito = [];
  $('#app').hidden = true;
  $('#sesion').hidden = true;
  $('#pantalla-acceso').hidden = false;
  mostrarAcceso('login');
  document.body.className = '';
  history.replaceState(null, '', location.pathname);
  if (mensaje) avisar(mensaje, 'error');
}

function mostrarApp() {
  const { usuario } = sesion;
  document.body.className = `rol-${usuario.rol}`;
  $('#pantalla-acceso').hidden = true;
  $('#app').hidden = false;
  $('#sesion').hidden = false;
  $('#sesion-nombre').textContent = usuario.nombre;
  $('#sesion-rol').textContent = usuario.rol === 'admin' ? 'Administrador' : 'Cliente';
  $('#titulo-pedidos').textContent = esAdmin() ? 'Todos los pedidos' : 'Mis pedidos';

  const permitidas = VISTAS_POR_ROL[usuario.rol] ?? VISTAS_POR_ROL.cliente;
  document.querySelectorAll('.pestana').forEach((b) => { b.hidden = !permitidas.includes(b.dataset.vista); });

  const pedida = location.hash.slice(1);
  mostrarVista(permitidas.includes(pedida) ? pedida : permitidas[0]);
}

document.querySelectorAll('.acceso-pestana').forEach((b) => b.addEventListener('click', () => mostrarAcceso(b.dataset.acceso)));
document.querySelectorAll('[data-ir]').forEach((b) => b.addEventListener('click', () => mostrarAcceso(b.dataset.ir)));

document.querySelectorAll('.demo-cuenta').forEach((b) => b.addEventListener('click', () => {
  $('#form-login [name="email"]').value = b.dataset.email;
  // La cuenta de administrador no trae contraseña: es la de ADMIN_PASSWORD en el .env de quien despliega
  const campoClave = $('#form-login [name="password"]');
  campoClave.value = b.dataset.password ?? '';
  if (!campoClave.value) campoClave.focus();
}));

alEnviar($('#form-login'), async (datos) => {
  try {
    iniciarSesion(await api('/api/auth/login', { metodo: 'POST', cuerpo: datos }));
  } catch (error) {
    if (error.status === 403) pedirCodigo(datos.email); // la cuenta existe pero falta confirmar el correo
    throw error;
  }
  $('#form-login').reset();
});

// Registrarse no abre la sesión: primero hay que confirmar el correo con el código
alEnviar($('#form-registro'), async (datos) => {
  const respuesta = await api('/api/auth/registro', { metodo: 'POST', cuerpo: datos });
  $('#form-registro').reset();
  pedirCodigo(datos.email);
  avisar(respuesta.mensaje);
});

alEnviar($('#form-verificar'), async (datos) => {
  iniciarSesion(await api('/api/auth/verificar-correo', { metodo: 'POST', cuerpo: datos }));
  $('#form-verificar').reset();
});

$('#reenviar-codigo').addEventListener('click', async () => {
  try {
    const respuesta = await api('/api/auth/reenviar-codigo', { metodo: 'POST', cuerpo: { email: $('#form-verificar').elements.email.value } });
    avisar(respuesta.mensaje);
  } catch (error) {
    avisar(error.message, 'error');
  }
});

// Avisa al servidor para que el token deje de valer; si no responde, la sesión se cierra igual en el navegador
$('#cerrar-sesion').addEventListener('click', async () => {
  await api('/api/auth/logout', { metodo: 'POST' }).catch(() => {});
  cerrarSesion();
});

// ───────────── Pestañas ─────────────

const cargadores = {
  usuarios: cargarUsuarios,
  productos: cargarProductos,
  pedidos: cargarPedidos,
  actividad: cargarActividad,
};

function mostrarVista(vista) {
  vistaActual = vista;
  history.replaceState(null, '', `#${vista}`);
  document.querySelectorAll('.pestana').forEach((b) => b.classList.toggle('activa', b.dataset.vista === vista));
  document.querySelectorAll('.vista').forEach((s) => s.classList.toggle('activa', s.id === `vista-${vista}`));
  cargadores[vista]();
}

document.querySelectorAll('.pestana').forEach((boton) => {
  boton.addEventListener('click', () => mostrarVista(boton.dataset.vista));
});

// ───────────── Estado de los microservicios ─────────────

async function revisarEstado() {
  const resultados = await Promise.all(
    SERVICIOS.map((s) => fetch(`/estado/${s.id}`, { cache: 'no-store' }).then((r) => r.ok).catch(() => false))
  );
  $('#estado-servicios').innerHTML = SERVICIOS.map((s, i) => `
    <li class="${resultados[i] ? 'en-linea' : 'caido'}" title="${resultados[i] ? 'En línea' : 'Sin respuesta'}">
      <span class="punto"></span>${s.nombre} <small>${s.tecnologia}</small>
    </li>`).join('');
}

// ───────────── Usuarios (Python / FastAPI / PostgreSQL) — solo admin ─────────────

async function cargarUsuarios() {
  const cuerpo = $('#tabla-usuarios');
  try {
    usuarios = await api('/api/usuarios');
    cuerpo.innerHTML = usuarios.length
      ? usuarios.map((u) => `
          <tr>
            <td>${u.id}</td>
            <td>${esc(u.nombre)}</td>
            <td>${esc(u.email)}${u.email_verificado ? '' : '<span class="insignia sin-confirmar" title="Todavía no escribió el código que le llegó por correo">sin confirmar</span>'}</td>
            <td>${esc(u.telefono || '—')}</td>
            <td>${esc(u.ciudad || '—')}</td>
            <td><span class="insignia rol-${esc(u.rol)}">${u.rol === 'admin' ? 'Admin' : 'Cliente'}</span></td>
            <td class="acciones">${u.id === sesion.usuario.id ? '' : `
              <button class="boton-suave" data-cerrar-sesiones="${u.id}" title="Sus tokens dejan de valer al instante">Cerrar sesiones</button>
              <button class="boton-borrar" data-id="${u.id}">Eliminar</button>`}</td>
          </tr>`).join('')
      : filaVacia(7, 'No hay usuarios registrados');
  } catch (error) {
    cuerpo.innerHTML = filaVacia(7, error.message, true);
  }
}

alEnviar($('#form-usuario'), async (datos) => {
  const usuario = await api('/api/usuarios', { metodo: 'POST', cuerpo: datos });
  $('#form-usuario').reset();
  avisar(`Usuario "${usuario.nombre}" creado`);
  cargarUsuarios();
});

$('#tabla-usuarios').addEventListener('click', async (evento) => {
  const cerrar = evento.target.closest('[data-cerrar-sesiones]');
  if (cerrar) {
    const usuario = usuarios.find((u) => String(u.id) === cerrar.dataset.cerrarSesiones);
    if (!(await confirmar({
      titulo: 'Cerrar sus sesiones',
      mensaje: `${usuario?.nombre ?? 'Este usuario'} tendrá que volver a iniciar sesión en todos sus dispositivos.`,
      aceptar: 'Sí, cerrar sesiones',
    }))) return;
    try {
      await api(`/api/usuarios/${cerrar.dataset.cerrarSesiones}/cerrar-sesiones`, { metodo: 'POST' });
      avisar(`Sesiones de ${usuario?.nombre ?? 'el usuario'} cerradas`);
    } catch (error) {
      avisar(error.message, 'error');
    }
    return;
  }
  const boton = evento.target.closest('.boton-borrar');
  if (!boton) return;
  const usuario = usuarios.find((u) => String(u.id) === boton.dataset.id);
  if (!(await confirmar({
    titulo: 'Eliminar usuario',
    mensaje: `¿Seguro que quieres eliminar a ${usuario?.nombre ?? 'este usuario'}? Esta acción no se puede deshacer.`,
    aceptar: 'Sí, eliminar',
    peligro: true,
  }))) return;
  try {
    await api(`/api/usuarios/${boton.dataset.id}`, { metodo: 'DELETE' });
    avisar('Usuario eliminado');
    cargarUsuarios();
  } catch (error) {
    avisar(error.message, 'error');
  }
});

// ───────────── Productos (Node.js / Express / MongoDB) ─────────────

async function cargarProductos() {
  const cuerpo = $('#tabla-productos');
  try {
    productos = await api('/api/productos');
    cuerpo.innerHTML = productos.length
      ? productos.map((p) => `
          <tr>
            <td>${esc(p.nombre)}<small>${esc(p.descripcion)}</small></td>
            <td>${esc(p.categoria)}</td>
            <td class="num">${moneda.format(p.precio)}</td>
            <td class="num ${p.stock <= 5 ? 'stock-bajo' : ''}">${p.stock}</td>
            <td class="solo-admin"><button class="boton-borrar" data-id="${esc(p.id)}">Eliminar</button></td>
          </tr>`).join('')
      : filaVacia(5, 'No hay productos en el catálogo');
  } catch (error) {
    cuerpo.innerHTML = filaVacia(5, error.message, true);
  }
}

alEnviar($('#form-producto'), async (datos) => {
  const producto = await api('/api/productos', {
    metodo: 'POST',
    cuerpo: { ...datos, precio: Number(datos.precio), stock: Number(datos.stock ?? 0) },
  });
  $('#form-producto').reset();
  avisar(`Producto "${producto.nombre}" creado`);
  cargarProductos();
});

$('#tabla-productos').addEventListener('click', async (evento) => {
  const boton = evento.target.closest('.boton-borrar');
  if (!boton) return;
  const producto = productos.find((p) => p.id === boton.dataset.id);
  if (!(await confirmar({
    titulo: 'Eliminar producto',
    mensaje: `¿Seguro que quieres eliminar "${producto?.nombre ?? 'este producto'}" del catálogo? Esta acción no se puede deshacer.`,
    aceptar: 'Sí, eliminar',
    peligro: true,
  }))) return;
  try {
    await api(`/api/productos/${boton.dataset.id}`, { metodo: 'DELETE' });
    avisar('Producto eliminado');
    cargarProductos();
  } catch (error) {
    avisar(error.message, 'error');
  }
});

// ───────────── Pedidos (Java / Spring Boot / PostgreSQL) ─────────────

function llenarSelect(select, elementos, texto, valor, vacio) {
  const actual = select.value;
  select.innerHTML = elementos.length
    ? elementos.map((e) => `<option value="${esc(valor(e))}">${esc(texto(e))}</option>`).join('')
    : `<option value="">${esc(vacio)}</option>`;
  if (elementos.some((e) => String(valor(e)) === actual)) select.value = actual;
}

function dibujarCarrito() {
  $('#carrito').innerHTML = carrito.length
    ? carrito.map((item, i) => `
        <li>
          <span>${item.cantidad} × ${esc(item.nombre)}</span>
          <span class="num">${moneda.format(item.precio * item.cantidad)}</span>
          <button type="button" class="quitar" data-indice="${i}" title="Quitar">✕</button>
        </li>`).join('')
    : '<li class="vacio">Agrega uno o más productos al pedido</li>';
  $('#total-carrito').textContent = moneda.format(carrito.reduce((suma, i) => suma + i.precio * i.cantidad, 0));
}

$('#agregar-item').addEventListener('click', () => {
  const producto = productos.find((p) => p.id === $('#pedido-producto').value);
  const cantidad = Number($('#pedido-cantidad').value);
  if (!producto) return avisar('Elige un producto', 'error');
  if (!Number.isInteger(cantidad) || cantidad < 1) return avisar('La cantidad debe ser un entero mayor que 0', 'error');

  const existente = carrito.find((i) => i.productoId === producto.id);
  if (existente) existente.cantidad += cantidad;
  else carrito.push({ productoId: producto.id, nombre: producto.nombre, precio: producto.precio, cantidad });
  $('#pedido-cantidad').value = 1;
  dibujarCarrito();
});

$('#carrito').addEventListener('click', (evento) => {
  const boton = evento.target.closest('.quitar');
  if (!boton) return;
  carrito.splice(Number(boton.dataset.indice), 1);
  dibujarCarrito();
});

function celdaEstado(p) {
  if (esAdmin() && !ESTADOS_FINALES.includes(p.estado)) {
    return `<select class="selector-estado estado-${p.estado}" data-id="${p.id}">
      ${ESTADOS_ELEGIBLES.map((e) => `<option ${e === p.estado ? 'selected' : ''}>${e}</option>`).join('')}
    </select>`;
  }
  return `<span class="insignia estado-${p.estado}">${p.estado}</span>`;
}

function celdaAcciones(p) {
  if (esAdmin()) return `<button class="boton-borrar" data-id="${p.id}">Eliminar</button>`;
  if (p.estado === 'PENDIENTE') return `<button class="boton-borrar" data-cancelar="${p.id}">Cancelar</button>`;
  return '';
}

async function cargarPedidos() {
  const cuerpo = $('#tabla-pedidos');
  const [resUsuarios, resProductos, resPedidos] = await Promise.allSettled([
    esAdmin() ? api('/api/usuarios') : Promise.resolve([]),
    api('/api/productos'),
    api('/api/pedidos'),
  ]);
  if (resUsuarios.status === 'fulfilled') usuarios = resUsuarios.value;
  if (resProductos.status === 'fulfilled') productos = resProductos.value;

  llenarSelect($('#pedido-usuario'), usuarios, (u) => `${u.nombre} (#${u.id})`, (u) => u.id, 'No hay usuarios');
  llenarSelect(
    $('#pedido-producto'),
    productos,
    (p) => `${p.nombre} — ${moneda.format(p.precio)} (${p.stock} disp.)`,
    (p) => p.id,
    'No hay productos'
  );
  dibujarCarrito();

  if (resPedidos.status === 'rejected') {
    cuerpo.innerHTML = filaVacia(7, resPedidos.reason.message, true);
    return;
  }
  const pedidos = resPedidos.value;
  cuerpo.innerHTML = pedidos.length
    ? pedidos.map((p) => `
        <tr>
          <td>${p.id}</td>
          <td>${fechaHora.format(new Date(p.fecha))}</td>
          <td>${esc(p.usuarioNombre)}</td>
          <td><ul class="items">${p.items.map((i) => `
            <li>${i.cantidad} × ${esc(i.productoNombre)} <small>${moneda.format(i.subtotal)}</small></li>`).join('')}
          </ul></td>
          <td class="num">${moneda.format(p.total)}</td>
          <td>${celdaEstado(p)}</td>
          <td>${celdaAcciones(p)}</td>
        </tr>`).join('')
    : filaVacia(7, esAdmin() ? 'Todavía no hay pedidos' : 'Todavía no has hecho pedidos');
}

alEnviar($('#form-pedido'), async (datos) => {
  if (!carrito.length) throw new Error('Agrega al menos un producto al pedido');
  const cuerpo = { items: carrito.map(({ productoId, cantidad }) => ({ productoId, cantidad })) };
  if (esAdmin()) cuerpo.usuarioId = Number(datos.usuarioId);
  const pedido = await api('/api/pedidos', { metodo: 'POST', cuerpo });
  carrito = [];
  avisar(`Pedido #${pedido.id} creado — total ${moneda.format(pedido.total)}`);
  cargarPedidos();
});

async function cambiarEstado(id, estado) {
  try {
    const pedido = await api(`/api/pedidos/${id}/estado`, { metodo: 'PATCH', cuerpo: { estado } });
    avisar(`Pedido #${pedido.id}: ${pedido.estado}${pedido.estado === 'CANCELADO' ? ' (stock devuelto)' : ''}`);
  } catch (error) {
    avisar(error.message, 'error');
  }
  cargarPedidos();
}

$('#tabla-pedidos').addEventListener('change', (evento) => {
  const select = evento.target.closest('.selector-estado');
  if (select) cambiarEstado(select.dataset.id, select.value);
});

$('#tabla-pedidos').addEventListener('click', async (evento) => {
  const cancelar = evento.target.closest('[data-cancelar]');
  if (cancelar) {
    const confirmado = await confirmar({
      titulo: `Cancelar el pedido #${cancelar.dataset.cancelar}`,
      mensaje: 'Los productos volverán al catálogo y el pedido quedará cancelado. Esta acción no se puede deshacer.',
      aceptar: 'Sí, cancelar pedido',
      cancelar: 'No, volver',
      peligro: true,
    });
    if (confirmado) cambiarEstado(cancelar.dataset.cancelar, 'CANCELADO');
    return;
  }
  const boton = evento.target.closest('.boton-borrar');
  if (!boton) return;
  if (!(await confirmar({
    titulo: `Eliminar el pedido #${boton.dataset.id}`,
    mensaje: 'Se quitará del historial. Si todavía estaba pendiente, sus productos vuelven al catálogo.',
    aceptar: 'Sí, eliminar',
    peligro: true,
  }))) return;
  try {
    await api(`/api/pedidos/${boton.dataset.id}`, { metodo: 'DELETE' });
    avisar('Pedido eliminado');
    cargarPedidos();
  } catch (error) {
    avisar(error.message, 'error');
  }
});

// ───────────── Actividad (Go / MongoDB) — solo admin ─────────────

async function cargarActividad() {
  try {
    const [resumen, eventos] = await Promise.all([api('/api/eventos/resumen'), api('/api/eventos?limite=40')]);
    $('#resumen-actividad').innerHTML =
      `<div class="cifra"><strong>${resumen.total}</strong><span>eventos en total</span></div>` +
      (resumen.por_servicio || []).map((f) => `
        <div class="cifra servicio-${esc(f.servicio)}"><strong>${f.total}</strong><span>${esc(f.servicio)}</span></div>`).join('');

    $('#lista-eventos').innerHTML = eventos.length
      ? eventos.map((e) => `
          <li>
            <span class="etiqueta servicio-${esc(e.servicio)}">${esc(e.servicio)}</span>
            <div><strong>${esc(e.tipo)}</strong><p>${esc(e.mensaje)}</p></div>
            <time datetime="${esc(e.fecha)}">${fechaHora.format(new Date(e.fecha))}</time>
          </li>`).join('')
      : '<li class="vacio">Aún no hay eventos. Crea un usuario, un producto o un pedido.</li>';
  } catch (error) {
    $('#resumen-actividad').innerHTML = '';
    $('#lista-eventos').innerHTML = `<li class="vacio error-carga">${esc(error.message)}</li>`;
  }
}

// ───────────── Inicio ─────────────

revisarEstado();
setInterval(revisarEstado, 10000);
setInterval(() => { if (sesion && vistaActual === 'actividad') cargarActividad(); }, 5000);

if (sesion) mostrarApp();
else cerrarSesion();
