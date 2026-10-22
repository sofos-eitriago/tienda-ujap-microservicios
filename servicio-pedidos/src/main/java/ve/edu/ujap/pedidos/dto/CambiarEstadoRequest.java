package ve.edu.ujap.pedidos.dto;

import jakarta.validation.constraints.NotNull;
import ve.edu.ujap.pedidos.modelo.EstadoPedido;

public record CambiarEstadoRequest(@NotNull(message = "estado es obligatorio") EstadoPedido estado) {
}
