package ve.edu.ujap.pedidos.modelo;

import jakarta.persistence.CascadeType;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.FetchType;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.OneToMany;
import jakarta.persistence.OrderBy;
import jakarta.persistence.PrePersist;
import jakarta.persistence.PreUpdate;
import jakarta.persistence.Table;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;

/**
 * Tabla "pedidos" en PostgreSQL. Cada pedido tiene uno o más productos (tabla "pedido_items").
 * Se guarda una copia del nombre del usuario y de los productos: así el historial
 * no depende de que los otros microservicios estén disponibles al consultarlo.
 */
@Entity
@Table(name = "pedidos")
public class Pedido {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false)
    private Long usuarioId;

    @Column(nullable = false, length = 100)
    private String usuarioNombre;

    @OneToMany(mappedBy = "pedido", cascade = CascadeType.ALL, orphanRemoval = true, fetch = FetchType.EAGER)
    @OrderBy("id")
    private List<PedidoItem> items = new ArrayList<>();

    @Column(nullable = false, precision = 12, scale = 2)
    private BigDecimal total = BigDecimal.ZERO;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 20)
    private EstadoPedido estado = EstadoPedido.PROCESANDO;

    @Column(nullable = false, updatable = false)
    private Instant fecha;

    @Column(nullable = false)
    private Instant actualizado;

    @PrePersist
    void alCrear() {
        fecha = Instant.now();
        actualizado = fecha;
    }

    @PreUpdate
    void alActualizar() {
        actualizado = Instant.now();
    }

    public void agregarItem(PedidoItem item) {
        item.setPedido(this);
        items.add(item);
        total = total.add(item.getSubtotal());
    }

    /** Referencia única de la reserva de stock de un producto de este pedido (para que sea idempotente). */
    public String referenciaStock(PedidoItem item) {
        return "pedido-" + id + "-" + item.getProductoId();
    }

    public Long getId() { return id; }

    public Long getUsuarioId() { return usuarioId; }
    public void setUsuarioId(Long usuarioId) { this.usuarioId = usuarioId; }

    public String getUsuarioNombre() { return usuarioNombre; }
    public void setUsuarioNombre(String usuarioNombre) { this.usuarioNombre = usuarioNombre; }

    public List<PedidoItem> getItems() { return items; }

    public BigDecimal getTotal() { return total; }

    public EstadoPedido getEstado() { return estado; }
    public void setEstado(EstadoPedido estado) { this.estado = estado; }

    public Instant getFecha() { return fecha; }

    public Instant getActualizado() { return actualizado; }
}
