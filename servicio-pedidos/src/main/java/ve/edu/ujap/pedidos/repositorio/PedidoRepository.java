package ve.edu.ujap.pedidos.repositorio;

import org.springframework.data.jpa.repository.JpaRepository;
import ve.edu.ujap.pedidos.modelo.EstadoPedido;
import ve.edu.ujap.pedidos.modelo.Pedido;

import java.time.Instant;
import java.util.List;

// Spring Data genera las consultas a partir del nombre de cada método
public interface PedidoRepository extends JpaRepository<Pedido, Long> {

    List<Pedido> findAllByOrderByFechaDesc();

    List<Pedido> findByUsuarioIdOrderByFechaDesc(Long usuarioId);

    List<Pedido> findByEstadoAndActualizadoBefore(EstadoPedido estado, Instant limite);
}
