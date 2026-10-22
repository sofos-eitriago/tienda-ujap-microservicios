package ve.edu.ujap.pedidos.modelo;

public enum EstadoPedido {
    /** Interno: se está reservando el stock. Si se queda aquí, la recuperación automática lo resuelve. */
    PROCESANDO,
    PENDIENTE,
    ENVIADO,
    ENTREGADO,
    CANCELADO,
    /** No se pudo completar (falló la reserva de stock); el stock ya fue devuelto. */
    RECHAZADO
}
