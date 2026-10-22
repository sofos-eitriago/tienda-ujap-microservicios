package ve.edu.ujap.pedidos.servicio;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;
import ve.edu.ujap.pedidos.modelo.EstadoPedido;
import ve.edu.ujap.pedidos.modelo.Pedido;
import ve.edu.ujap.pedidos.repositorio.PedidoRepository;

import java.time.Duration;
import java.time.Instant;

/**
 * Tarea periódica que repara pedidos que quedaron a medias (estado PROCESANDO), por ejemplo
 * si el servicio se reinició mientras reservaba stock o si el servicio de productos estaba caído
 * justo cuando había que deshacer una reserva. Libera su stock (de forma idempotente) y los marca RECHAZADO.
 */
@Component
public class RecuperacionPedidos {

    private static final Logger log = LoggerFactory.getLogger(RecuperacionPedidos.class);

    private final PedidoRepository repositorio;
    private final PedidoService pedidos;
    private final Duration antiguedad;

    public RecuperacionPedidos(PedidoRepository repositorio, PedidoService pedidos,
                               @Value("${pedidos.recuperacion.antiguedad-seg}") long antiguedadSeg) {
        this.repositorio = repositorio;
        this.pedidos = pedidos;
        this.antiguedad = Duration.ofSeconds(antiguedadSeg);
    }

    @Scheduled(fixedDelayString = "${pedidos.recuperacion.intervalo-ms}", initialDelay = 20_000)
    public void revisar() {
        for (Pedido pedido : repositorio.findByEstadoAndActualizadoBefore(EstadoPedido.PROCESANDO, Instant.now().minus(antiguedad))) {
            try {
                pedidos.recuperar(pedido);
                log.info("Pedido {} recuperado: stock devuelto y marcado RECHAZADO", pedido.getId());
            } catch (RuntimeException e) {
                log.warn("No se pudo recuperar el pedido {} (se reintentará): {}", pedido.getId(), e.getMessage());
            }
        }
    }
}
