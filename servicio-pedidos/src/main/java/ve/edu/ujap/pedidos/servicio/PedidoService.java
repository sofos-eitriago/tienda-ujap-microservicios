package ve.edu.ujap.pedidos.servicio;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.web.server.ResponseStatusException;
import ve.edu.ujap.pedidos.dto.CrearPedidoRequest;
import ve.edu.ujap.pedidos.dto.ItemPedidoRequest;
import ve.edu.ujap.pedidos.integracion.ProductoRemoto;
import ve.edu.ujap.pedidos.integracion.ServiciosExternos;
import ve.edu.ujap.pedidos.integracion.UsuarioRemoto;
import ve.edu.ujap.pedidos.modelo.EstadoPedido;
import ve.edu.ujap.pedidos.modelo.Pedido;
import ve.edu.ujap.pedidos.modelo.PedidoItem;
import ve.edu.ujap.pedidos.repositorio.PedidoRepository;
import ve.edu.ujap.pedidos.seguridad.Identidad;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;

@Service
public class PedidoService {

    private static final Logger log = LoggerFactory.getLogger(PedidoService.class);
    private static final Set<EstadoPedido> ESTADOS_ELEGIBLES =
            Set.of(EstadoPedido.PENDIENTE, EstadoPedido.ENVIADO, EstadoPedido.ENTREGADO, EstadoPedido.CANCELADO);

    private final PedidoRepository repositorio;
    private final ServiciosExternos servicios;

    public PedidoService(PedidoRepository repositorio, ServiciosExternos servicios) {
        this.repositorio = repositorio;
        this.servicios = servicios;
    }

    /** Un administrador ve todos (u opcionalmente los de un usuario); un cliente solo los suyos. */
    public List<Pedido> listar(Identidad yo, Long usuarioId) {
        if (!yo.esAdmin()) {
            return repositorio.findByUsuarioIdOrderByFechaDesc(idDelCliente(yo));
        }
        return usuarioId == null
                ? repositorio.findAllByOrderByFechaDesc()
                : repositorio.findByUsuarioIdOrderByFechaDesc(usuarioId);
    }

    public Pedido obtener(Identidad yo, Long id) {
        Pedido pedido = buscar(id);
        if (!yo.esAdmin() && !pedido.getUsuarioId().equals(yo.usuarioId())) {
            throw noEncontrado(id); // no se revela que existe un pedido de otra persona
        }
        return pedido;
    }

    /**
     * Crear un pedido involucra a los cuatro microservicios y se hace en pasos que toleran fallos:
     *  1. Usuarios (Python): el usuario debe existir.
     *  2. Productos (Node):  se obtienen nombres y precios.
     *  3. Se guarda el pedido como PROCESANDO (así queda constancia aunque el servicio se caiga).
     *  4. Productos (Node):  se reserva el stock de cada producto con una referencia única.
     *     Si alguno falla, se libera lo ya reservado y el pedido se descarta.
     *  5. El pedido pasa a PENDIENTE y se registra el evento en Actividad (Go).
     * Si el proceso se interrumpe entre 3 y 5, RecuperacionPedidos lo resuelve después.
     */
    public Pedido crear(Identidad yo, CrearPedidoRequest solicitud) {
        Long usuarioId = yo.esAdmin() ? solicitud.usuarioId() : idDelCliente(yo);
        if (usuarioId == null) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "usuarioId es obligatorio cuando el pedido lo crea un administrador");
        }
        UsuarioRemoto usuario = servicios.obtenerUsuario(usuarioId);

        // Si el mismo producto aparece varias veces, se suman las cantidades
        Map<String, Integer> cantidades = new LinkedHashMap<>();
        for (ItemPedidoRequest item : solicitud.items()) {
            cantidades.merge(item.productoId(), item.cantidad(), Integer::sum);
        }

        Pedido pedido = new Pedido();
        pedido.setUsuarioId(usuario.id());
        pedido.setUsuarioNombre(usuario.nombre());
        cantidades.forEach((productoId, cantidad) -> {
            ProductoRemoto producto = servicios.obtenerProducto(productoId);
            pedido.agregarItem(new PedidoItem(producto.id(), producto.nombre(), cantidad, producto.precio()));
        });

        Pedido guardado = repositorio.save(pedido); // estado PROCESANDO
        try {
            for (PedidoItem item : guardado.getItems()) {
                servicios.reservarStock(item.getProductoId(), item.getCantidad(), guardado.referenciaStock(item));
            }
        } catch (ResponseStatusException e) {
            descartar(guardado);
            throw e;
        }

        guardado.setEstado(EstadoPedido.PENDIENTE);
        guardado = repositorio.save(guardado);

        servicios.registrarEvento("PEDIDO_CREADO",
                String.format("Pedido #%d de %s: %d producto(s), total $%s",
                        guardado.getId(), guardado.getUsuarioNombre(), guardado.getItems().size(), guardado.getTotal()),
                Map.of("pedido_id", guardado.getId(), "usuario_id", guardado.getUsuarioId(), "total", guardado.getTotal()));
        return guardado;
    }

    public Pedido cambiarEstado(Identidad yo, Long id, EstadoPedido nuevoEstado) {
        Pedido pedido = obtener(yo, id);

        if (!ESTADOS_ELEGIBLES.contains(nuevoEstado)) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "Estado no permitido: " + nuevoEstado);
        }
        if (!yo.esAdmin() && !(nuevoEstado == EstadoPedido.CANCELADO && pedido.getEstado() == EstadoPedido.PENDIENTE)) {
            throw new ResponseStatusException(HttpStatus.FORBIDDEN, "Solo puedes cancelar tus pedidos que estén PENDIENTES");
        }
        switch (pedido.getEstado()) {
            case CANCELADO, RECHAZADO -> throw new ResponseStatusException(HttpStatus.CONFLICT,
                    "El pedido " + id + " está " + pedido.getEstado() + " y ya no se puede modificar");
            case PROCESANDO -> throw new ResponseStatusException(HttpStatus.CONFLICT, "El pedido " + id + " todavía se está procesando");
            case ENTREGADO -> {
                if (nuevoEstado == EstadoPedido.CANCELADO) {
                    throw new ResponseStatusException(HttpStatus.CONFLICT, "Un pedido entregado no se puede cancelar");
                }
            }
            default -> { }
        }
        if (pedido.getEstado() == nuevoEstado) {
            return pedido;
        }

        if (nuevoEstado == EstadoPedido.CANCELADO) {
            liberarStock(pedido);
        }
        EstadoPedido anterior = pedido.getEstado();
        pedido.setEstado(nuevoEstado);
        pedido = repositorio.save(pedido);

        servicios.registrarEvento("PEDIDO_" + nuevoEstado.name(),
                String.format("Pedido #%d: %s → %s (por %s)", pedido.getId(), anterior, nuevoEstado, nombre(yo)),
                Map.of("pedido_id", pedido.getId(), "estado", nuevoEstado.name()));
        return pedido;
    }

    public void eliminar(Identidad yo, Long id) {
        exigirAdmin(yo);
        Pedido pedido = buscar(id);
        if (pedido.getEstado() == EstadoPedido.PENDIENTE || pedido.getEstado() == EstadoPedido.PROCESANDO) {
            liberarStock(pedido); // el pedido desaparece: su stock vuelve al catálogo
        }
        repositorio.delete(pedido);
        servicios.registrarEvento("PEDIDO_ELIMINADO",
                String.format("Pedido #%d eliminado (por %s)", id, nombre(yo)),
                Map.of("pedido_id", id));
    }

    // ─────────────── Usado por RecuperacionPedidos ───────────────

    /** Libera el stock de un pedido que quedó en PROCESANDO y lo marca RECHAZADO. */
    public void recuperar(Pedido pedido) {
        liberarStock(pedido);
        pedido.setEstado(EstadoPedido.RECHAZADO);
        repositorio.save(pedido);
        servicios.registrarEvento("PEDIDO_RECHAZADO",
                String.format("Pedido #%d quedó incompleto: se devolvió el stock y se marcó RECHAZADO", pedido.getId()),
                Map.of("pedido_id", pedido.getId()));
    }

    // ─────────────── Auxiliares ───────────────

    /** Intenta deshacer un pedido que no se pudo completar. Si no se puede, queda para la recuperación automática. */
    private void descartar(Pedido pedido) {
        try {
            liberarStock(pedido);
            repositorio.delete(pedido);
        } catch (RuntimeException e) {
            log.warn("No se pudo deshacer el pedido {} ahora; la recuperación automática lo resolverá: {}", pedido.getId(), e.getMessage());
        }
    }

    /** Liberar es idempotente: solo devuelve stock de las reservas que realmente se aplicaron. */
    private void liberarStock(Pedido pedido) {
        for (PedidoItem item : pedido.getItems()) {
            try {
                servicios.liberarStock(item.getProductoId(), item.getCantidad(), pedido.referenciaStock(item));
            } catch (ResponseStatusException e) {
                // Si el producto ya fue eliminado del catálogo no hay stock que devolver
                if (e.getStatusCode() != HttpStatus.BAD_REQUEST) {
                    throw e;
                }
            }
        }
    }

    private Pedido buscar(Long id) {
        return repositorio.findById(id).orElseThrow(() -> noEncontrado(id));
    }

    private static ResponseStatusException noEncontrado(Long id) {
        return new ResponseStatusException(HttpStatus.NOT_FOUND, "Pedido " + id + " no encontrado");
    }

    private static Long idDelCliente(Identidad yo) {
        if (yo.usuarioId() == null) {
            throw new ResponseStatusException(HttpStatus.FORBIDDEN, "Este token no pertenece a un usuario");
        }
        return yo.usuarioId();
    }

    private static void exigirAdmin(Identidad yo) {
        if (!yo.esAdmin()) {
            throw new ResponseStatusException(HttpStatus.FORBIDDEN, "No tienes permiso para esta operación");
        }
    }

    private static String nombre(Identidad yo) {
        return yo.nombre() != null ? yo.nombre() : yo.sub();
    }
}
