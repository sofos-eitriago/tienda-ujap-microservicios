// Modelo Mongoose: colección "productos" en MongoDB
const { Schema, model } = require('mongoose');

const productoSchema = new Schema(
  {
    nombre: { type: String, required: [true, 'El nombre es obligatorio'], trim: true, maxlength: 120 },
    descripcion: { type: String, trim: true, default: '' },
    categoria: { type: String, trim: true, default: 'General' },
    precio: {
      type: Number,
      required: [true, 'El precio es obligatorio'],
      min: [0, 'El precio no puede ser negativo'],
    },
    stock: {
      type: Number,
      default: 0,
      min: [0, 'El stock no puede ser negativo'],
      validate: { validator: Number.isInteger, message: 'El stock debe ser un número entero' },
    },
    // Referencias de las reservas ("R:...") y liberaciones ("L:...") ya aplicadas.
    // Hacen que reservar/liberar sean idempotentes: repetir la misma operación no cambia el stock dos veces.
    // No se devuelven en las consultas (select: false).
    movimientos: { type: [String], default: [], select: false },
  },
  { timestamps: true, versionKey: false }
);

// En JSON se expone "id" (texto) en lugar de "_id"
productoSchema.set('toJSON', {
  virtuals: true,
  transform: (_doc, ret) => {
    delete ret._id;
    delete ret.movimientos;
    return ret;
  },
});

module.exports = model('Producto', productoSchema);
