package ve.edu.ujap.pedidos.dto;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.Size;

import java.util.List;

/**
 * usuarioId solo lo usa un administrador (para crear un pedido a nombre de otro usuario).
 * Un cliente siempre crea pedidos a su propio nombre: se toma del token.
 */
public record CrearPedidoRequest(
        Long usuarioId,
        @NotEmpty(message = "El pedido debe tener al menos un producto")
        @Size(max = 20, message = "Un pedido admite como máximo 20 productos distintos")
        List<@Valid ItemPedidoRequest> items
) {
}
