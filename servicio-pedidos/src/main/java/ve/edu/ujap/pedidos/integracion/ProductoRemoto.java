package ve.edu.ujap.pedidos.integracion;

import java.math.BigDecimal;

// Respuesta de GET /api/productos/{id} del servicio de productos (Node.js)
public record ProductoRemoto(String id, String nombre, BigDecimal precio, Integer stock) {
}
