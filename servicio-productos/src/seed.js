// Productos de ejemplo que se cargan solo si la colección está vacía
const Producto = require('./producto.model');

const PRODUCTOS_INICIALES = [
  { nombre: 'Laptop Lenovo IdeaPad 3', categoria: 'Computación', precio: 549.99, stock: 8, descripcion: 'Ryzen 5, 16 GB RAM, 512 GB SSD' },
  { nombre: 'Mouse inalámbrico Logitech M185', categoria: 'Accesorios', precio: 15.5, stock: 40, descripcion: 'Receptor USB, 1 año de batería' },
  { nombre: 'Teclado mecánico Redragon Kumara', categoria: 'Accesorios', precio: 39.9, stock: 25, descripcion: 'Switches rojos, retroiluminado' },
  { nombre: 'Monitor Samsung 24"', categoria: 'Computación', precio: 129.0, stock: 12, descripcion: 'Full HD, 75 Hz, panel IPS' },
  { nombre: 'Audífonos JBL Tune 510BT', categoria: 'Audio', precio: 45.0, stock: 18, descripcion: 'Bluetooth 5.0, 40 h de batería' },
  { nombre: 'Disco SSD Kingston 1 TB', categoria: 'Almacenamiento', precio: 69.99, stock: 3, descripcion: 'NVMe PCIe 4.0' },
];

async function sembrarProductos() {
  if ((await Producto.estimatedDocumentCount()) > 0) return;
  await Producto.insertMany(PRODUCTOS_INICIALES);
  console.log('Productos de ejemplo creados');
}

module.exports = { sembrarProductos };
