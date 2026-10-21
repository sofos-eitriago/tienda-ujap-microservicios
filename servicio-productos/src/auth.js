// Verificación de tokens JWT emitidos por el servicio de usuarios (mismo secreto compartido)
const jwt = require('jsonwebtoken');

const JWT_SECRET = process.env.JWT_SECRET || 'secreto-de-desarrollo-cambiar-en-produccion-2026';
if (JWT_SECRET.length < 32) throw new Error('JWT_SECRET debe tener al menos 32 caracteres');

function autenticar(req, res, next) {
  const [esquema, token] = (req.headers.authorization || '').split(' ');
  if (esquema !== 'Bearer' || !token) {
    return res.status(401).json({ detail: 'Falta el token de acceso (Authorization: Bearer <token>)' });
  }
  try {
    req.identidad = jwt.verify(token, JWT_SECRET, { algorithms: ['HS256'] });
    next();
  } catch (err) {
    const mensaje = err.name === 'TokenExpiredError' ? 'El token expiró, inicia sesión de nuevo' : 'Token inválido';
    res.status(401).json({ detail: mensaje });
  }
}

// Uso: router.post('/', ...requiereRol('admin'), manejador)
function requiereRol(...roles) {
  return [
    autenticar,
    (req, res, next) => {
      if (!roles.includes(req.identidad.rol)) {
        return res.status(403).json({ detail: 'No tienes permiso para esta operación' });
      }
      next();
    },
  ];
}

// Token corto con el que este servicio se identifica ante otros microservicios
function tokenServicio() {
  return jwt.sign({ rol: 'servicio' }, JWT_SECRET, { algorithm: 'HS256', subject: 'servicio-productos', expiresIn: '5m' });
}

module.exports = { requiereRol, tokenServicio };
