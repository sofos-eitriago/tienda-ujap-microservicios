// Microservicio de Productos — Node.js + Express + Mongoose + MongoDB
const express = require('express');
const mongoose = require('mongoose');
const productosRouter = require('./productos.routes');
const { sembrarProductos } = require('./seed');

const PORT = process.env.PORT || 3000;
const MONGO_URL = process.env.MONGO_URL || 'mongodb://localhost:27017/tienda';

const app = express();
app.use(express.json());

app.get('/health', (req, res) => {
  const conectado = mongoose.connection.readyState === 1;
  res.status(conectado ? 200 : 503).json({
    status: conectado ? 'ok' : 'sin conexión a MongoDB',
    servicio: 'productos',
    lenguaje: 'Node.js/Express',
  });
});

app.use('/api/productos', productosRouter);

app.use((req, res) => {
  res.status(404).json({ detail: `Ruta ${req.method} ${req.originalUrl} no existe` });
});

// Express 5 envía aquí también los errores de las funciones async
app.use((err, req, res, _next) => {
  if (err instanceof mongoose.Error.ValidationError) {
    return res.status(400).json({ detail: Object.values(err.errors).map((e) => e.message).join('; ') });
  }
  if (err instanceof mongoose.Error.CastError) {
    return res.status(400).json({ detail: `Valor inválido para "${err.path}"` });
  }
  if (err.type === 'entity.parse.failed') {
    return res.status(400).json({ detail: 'El cuerpo de la petición no es un JSON válido' });
  }
  console.error(err);
  res.status(500).json({ detail: 'Error interno del servidor' });
});

async function conectarMongo(intentos = 15) {
  for (let intento = 1; ; intento++) {
    try {
      await mongoose.connect(MONGO_URL, { serverSelectionTimeoutMS: 5000 });
      console.log('Conectado a MongoDB');
      return;
    } catch (err) {
      if (intento >= intentos) throw err;
      console.log(`MongoDB no disponible (intento ${intento}), reintentando...`);
      await new Promise((r) => setTimeout(r, 2000));
    }
  }
}

async function iniciar() {
  await conectarMongo();
  await sembrarProductos();
  app.listen(PORT, () => console.log(`Servicio de productos escuchando en el puerto ${PORT}`));
}

iniciar().catch((err) => {
  console.error('No se pudo iniciar el servicio:', err);
  process.exit(1);
});
