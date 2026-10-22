// Productos de ejemplo que se cargan solo si la colección está vacía
const Producto = require('./producto.model');

const PRODUCTOS_INICIALES = [
  // ── Computación ──
  { nombre: 'Laptop Lenovo IdeaPad 3', categoria: 'Computación', precio: 549.99, stock: 30, descripcion: 'Ryzen 5, 16 GB RAM, 512 GB SSD' },
  { nombre: 'Laptop HP Pavilion 15', categoria: 'Computación', precio: 649.9, stock: 20, descripcion: 'Core i5, 16 GB RAM, 512 GB SSD' },
  { nombre: 'Laptop ASUS VivoBook 14', categoria: 'Computación', precio: 519.0, stock: 25, descripcion: 'Ryzen 5, 8 GB RAM, 256 GB SSD' },
  { nombre: 'Mini PC Beelink SER5', categoria: 'Computación', precio: 299.0, stock: 15, descripcion: 'Ryzen 5, 16 GB RAM, 500 GB SSD' },
  { nombre: 'Monitor Samsung 24"', categoria: 'Computación', precio: 129.0, stock: 40, descripcion: 'Full HD, 75 Hz, panel IPS' },
  { nombre: 'Monitor LG UltraGear 27"', categoria: 'Computación', precio: 249.5, stock: 22, descripcion: 'QHD, 144 Hz, 1 ms' },

  // ── Accesorios ──
  { nombre: 'Mouse inalámbrico Logitech M185', categoria: 'Accesorios', precio: 15.5, stock: 150, descripcion: 'Receptor USB, 1 año de batería' },
  { nombre: 'Teclado mecánico Redragon Kumara', categoria: 'Accesorios', precio: 39.9, stock: 90, descripcion: 'Switches rojos, retroiluminado' },
  { nombre: 'Webcam Razer Kiyo X', categoria: 'Accesorios', precio: 49.9, stock: 45, descripcion: 'Full HD 1080p, enfoque automático' },
  { nombre: 'Hub USB-C 7 en 1 Anker', categoria: 'Accesorios', precio: 34.9, stock: 70, descripcion: 'HDMI 4K, USB 3.0 y lector SD' },
  { nombre: 'Mousepad XL Redragon', categoria: 'Accesorios', precio: 12.0, stock: 110, descripcion: '90 x 40 cm, base antideslizante' },
  { nombre: 'Soporte ajustable para laptop', categoria: 'Accesorios', precio: 22.5, stock: 60, descripcion: 'Aluminio, plegable, 6 alturas' },

  // ── Audio ──
  { nombre: 'Audífonos JBL Tune 510BT', categoria: 'Audio', precio: 45.0, stock: 80, descripcion: 'Bluetooth 5.0, 40 h de batería' },
  { nombre: 'Audífonos Sony WH-CH520', categoria: 'Audio', precio: 59.0, stock: 40, descripcion: 'Bluetooth, 50 h de batería, micrófono' },
  { nombre: 'Parlante JBL Flip 6', categoria: 'Audio', precio: 129.99, stock: 35, descripcion: 'Bluetooth, resistente al agua, 12 h' },
  { nombre: 'Micrófono USB HyperX SoloCast', categoria: 'Audio', precio: 54.9, stock: 30, descripcion: 'Condensador, patrón cardioide' },

  // ── Almacenamiento ──
  { nombre: 'Disco SSD Kingston 1 TB', categoria: 'Almacenamiento', precio: 69.99, stock: 60, descripcion: 'NVMe PCIe 4.0' },
  { nombre: 'Disco SSD Samsung 970 EVO 500 GB', categoria: 'Almacenamiento', precio: 64.0, stock: 40, descripcion: 'NVMe PCIe 3.0, hasta 3500 MB/s' },
  { nombre: 'Disco duro externo WD 2 TB', categoria: 'Almacenamiento', precio: 79.9, stock: 35, descripcion: 'USB 3.0, portátil' },
  { nombre: 'Memoria USB SanDisk 128 GB', categoria: 'Almacenamiento', precio: 11.9, stock: 200, descripcion: 'USB 3.2, hasta 150 MB/s' },

  // ── Redes ──
  { nombre: 'Router TP-Link Archer AX23', categoria: 'Redes', precio: 74.9, stock: 30, descripcion: 'Wi-Fi 6, AX1800, 4 antenas' },
  { nombre: 'Switch TP-Link 8 puertos Gigabit', categoria: 'Redes', precio: 24.9, stock: 45, descripcion: '10/100/1000 Mbps, carcasa metálica' },

  // ── Impresión ──
  { nombre: 'Impresora multifunción Epson EcoTank L3250', categoria: 'Impresión', precio: 229.0, stock: 18, descripcion: 'Tanque de tinta, Wi-Fi, escáner' },

  // ── Gaming ──
  { nombre: 'Control inalámbrico Xbox', categoria: 'Gaming', precio: 59.99, stock: 50, descripcion: 'Bluetooth, compatible con PC y consola' },
  { nombre: 'Silla gamer ergonómica', categoria: 'Gaming', precio: 189.0, stock: 12, descripcion: 'Reclinable, soporte lumbar, hasta 120 kg' },

  // ── Móviles y tablets ──
  { nombre: 'Tablet Samsung Galaxy Tab A9', categoria: 'Móviles y tablets', precio: 179.0, stock: 25, descripcion: 'Pantalla de 8.7", 64 GB' },
  { nombre: 'Smartphone Xiaomi Redmi 13', categoria: 'Móviles y tablets', precio: 169.0, stock: 40, descripcion: '8 GB RAM, 256 GB, cámara de 108 MP' },
  { nombre: 'Cargador rápido USB-C 65 W', categoria: 'Móviles y tablets', precio: 29.9, stock: 120, descripcion: 'GaN, 2 puertos, para laptop y teléfono' },
];

async function sembrarProductos() {
  if ((await Producto.estimatedDocumentCount()) > 0) return;
  await Producto.insertMany(PRODUCTOS_INICIALES);
  console.log(`Productos de ejemplo creados: ${PRODUCTOS_INICIALES.length}`);
}

module.exports = { sembrarProductos };
