package ve.edu.ujap.pedidos.dto;

import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

public record ItemPedidoRequest(
        @NotBlank(message = "productoId es obligatorio") String productoId,
        @NotNull(message = "cantidad es obligatoria")
        @Min(value = 1, message = "La cantidad debe ser al menos 1")
        @Max(value = 1000, message = "La cantidad máxima por producto es 1000")
        Integer cantidad
) {
}
