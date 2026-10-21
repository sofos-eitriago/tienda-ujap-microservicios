// Comunicación con el microservicio de actividad (Go)
const { tokenServicio } = require('./auth');

const ACTIVIDAD_URL = process.env.ACTIVIDAD_URL || 'http://localhost:8004';

// Envía un evento; si el servicio de actividad no responde, solo se deja constancia en el log.
async function registrarEvento(tipo, mensaje, datos = {}) {
  try {
    const respuesta = await fetch(`${ACTIVIDAD_URL}/api/eventos`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${tokenServicio()}` },
      body: JSON.stringify({ servicio: 'productos', tipo, mensaje, datos }),
      signal: AbortSignal.timeout(2000),
    });
    if (!respuesta.ok) throw new Error(`HTTP ${respuesta.status}`);
  } catch (err) {
    console.warn(`No se pudo registrar el evento en actividad: ${err.message}`);
  }
}

module.exports = { registrarEvento };
