// Rutas REST de /api/productos
const { Router } = require('express');
const Producto = require('./producto.model');
const { registrarEvento } = require('./actividad');
const { requiereRol } = require('./auth');

const router = Router();

const CAMPOS = ['nombre', 'descripcion', 'categoria', 'precio', 'stock'];
// Se conservan las últimas N referencias por producto (suficiente para cientos de pedidos activos)
const MAX_MOVIMIENTOS = 1000;

// Solo se aceptan los campos del modelo (evita que el cliente escriba _id, movimientos, etc.)
function tomarCampos(cuerpo = {}) {
  return Object.fromEntries(CAMPOS.filter((c) => cuerpo[c] !== undefined).map((c) => [c, cuerpo[c]]));
}

function noEncontrado(res, id) {
  return res.status(404).json({ detail: `Producto ${id} no encontrado` });
}

// Un id de MongoDB válido tiene 24 caracteres hexadecimales
router.param('id', (req, res, next, id) => {
  if (!/^[a-f\d]{24}$/i.test(id)) return noEncontrado(res, id);
  next();
});

// ───────────── Catálogo: lectura pública ─────────────

router.get('/', async (req, res) => {
  const filtro = {};
  if (req.query.categoria) filtro.categoria = req.query.categoria;
  if (req.query.q) {
    const texto = String(req.query.q).replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    filtro.nombre = { $regex: texto, $options: 'i' };
  }
  res.json(await Producto.find(filtro).sort({ nombre: 1 }));
});

router.get('/:id', async (req, res) => {
  const producto = await Producto.findById(req.params.id);
  if (!producto) return noEncontrado(res, req.params.id);
  res.json(producto);
});

// ───────────── Administración del catálogo: solo admin ─────────────

router.post('/', ...requiereRol('admin'), async (req, res) => {
  const producto = await Producto.create(tomarCampos(req.body));
  registrarEvento('PRODUCTO_CREADO', `Nuevo producto: ${producto.nombre}`, { producto_id: producto.id });
  res.status(201).json(producto);
});

router.put('/:id', ...requiereRol('admin'), async (req, res) => {
  const producto = await Producto.findByIdAndUpdate(req.params.id, tomarCampos(req.body), {
    new: true,
    runValidators: true,
  });
  if (!producto) return noEncontrado(res, req.params.id);
  registrarEvento('PRODUCTO_ACTUALIZADO', `Producto actualizado: ${producto.nombre}`, { producto_id: producto.id });
  res.json(producto);
});

router.delete('/:id', ...requiereRol('admin'), async (req, res) => {
  const producto = await Producto.findByIdAndDelete(req.params.id);
  if (!producto) return noEncontrado(res, req.params.id);
  registrarEvento('PRODUCTO_ELIMINADO', `Producto eliminado: ${producto.nombre}`, { producto_id: producto.id });
  res.status(204).send();
});

// ───────────── Stock: solo otros microservicios (rol "servicio") ─────────────
//
// Las usa el servicio de pedidos (Java). Cada operación lleva una "referencia" única
// (p. ej. "pedido-12-<idProducto>"). Todo ocurre en UNA sola operación atómica sobre el documento:
//   - reservar: descuenta si hay stock suficiente Y esa referencia no se aplicó antes.
//   - liberar:  devuelve solo si esa referencia SÍ se reservó Y todavía no se liberó.
// Así, reintentar una llamada (por un timeout o una caída) nunca descuenta ni devuelve dos veces.

function leerMovimiento(req, res) {
  const cantidad = Number(req.body?.cantidad);
  const referencia = String(req.body?.referencia ?? '').trim();
  if (!Number.isInteger(cantidad) || cantidad <= 0 || !referencia) {
    res.status(400).json({ detail: 'Se requiere "cantidad" (entero > 0) y "referencia"' });
    return null;
  }
  return { cantidad, referencia };
}

const agregarMovimiento = (marca) => ({ movimientos: { $each: [marca], $slice: -MAX_MOVIMIENTOS } });

router.post('/:id/reservar', ...requiereRol('servicio'), async (req, res) => {
  const movimiento = leerMovimiento(req, res);
  if (!movimiento) return;
  const { cantidad, referencia } = movimiento;
  const marca = `R:${referencia}`;

  const producto = await Producto.findOneAndUpdate(
    { _id: req.params.id, stock: { $gte: cantidad }, movimientos: { $ne: marca } },
    { $inc: { stock: -cantidad }, $push: agregarMovimiento(marca) },
    { new: true }
  );
  if (producto) return res.json({ aplicado: true, producto });

  const actual = await Producto.findById(req.params.id).select('+movimientos');
  if (!actual) return noEncontrado(res, req.params.id);
  if (actual.movimientos.includes(marca)) return res.json({ aplicado: false, repetido: true, producto: actual });
  res.status(409).json({ detail: `Stock insuficiente de "${actual.nombre}": hay ${actual.stock} y se pidieron ${cantidad}` });
});

router.post('/:id/liberar', ...requiereRol('servicio'), async (req, res) => {
  const movimiento = leerMovimiento(req, res);
  if (!movimiento) return;
  const { cantidad, referencia } = movimiento;
  const reserva = `R:${referencia}`;
  const liberacion = `L:${referencia}`;

  const producto = await Producto.findOneAndUpdate(
    { _id: req.params.id, $and: [{ movimientos: reserva }, { movimientos: { $ne: liberacion } }] },
    { $inc: { stock: cantidad }, $push: agregarMovimiento(liberacion) },
    { new: true }
  );
  if (producto) return res.json({ aplicado: true, producto });

  const actual = await Producto.findById(req.params.id);
  if (!actual) return noEncontrado(res, req.params.id);
  // No había nada que liberar: nunca se reservó o ya se había liberado
  res.json({ aplicado: false, producto: actual });
});

module.exports = router;
