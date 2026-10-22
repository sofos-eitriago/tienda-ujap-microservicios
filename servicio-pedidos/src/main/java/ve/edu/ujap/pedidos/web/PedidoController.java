package ve.edu.ujap.pedidos.web;

import jakarta.validation.Valid;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;
import ve.edu.ujap.pedidos.dto.CambiarEstadoRequest;
import ve.edu.ujap.pedidos.dto.CrearPedidoRequest;
import ve.edu.ujap.pedidos.modelo.Pedido;
import ve.edu.ujap.pedidos.seguridad.ServicioJwt;
import ve.edu.ujap.pedidos.servicio.PedidoService;

import java.util.List;

/** Todas las rutas exigen un token JWT; los permisos según el rol se aplican en PedidoService. */
@RestController
@RequestMapping("/api/pedidos")
public class PedidoController {

    private final PedidoService servicio;
    private final ServicioJwt jwt;

    public PedidoController(PedidoService servicio, ServicioJwt jwt) {
        this.servicio = servicio;
        this.jwt = jwt;
    }

    @GetMapping
    public List<Pedido> listar(@RequestHeader(value = HttpHeaders.AUTHORIZATION, required = false) String token,
                               @RequestParam(required = false) Long usuarioId) {
        return servicio.listar(jwt.autenticar(token), usuarioId);
    }

    @GetMapping("/{id}")
    public Pedido obtener(@RequestHeader(value = HttpHeaders.AUTHORIZATION, required = false) String token,
                          @PathVariable Long id) {
        return servicio.obtener(jwt.autenticar(token), id);
    }

    @PostMapping
    @ResponseStatus(HttpStatus.CREATED)
    public Pedido crear(@RequestHeader(value = HttpHeaders.AUTHORIZATION, required = false) String token,
                        @Valid @RequestBody CrearPedidoRequest solicitud) {
        return servicio.crear(jwt.autenticar(token), solicitud);
    }

    @PatchMapping("/{id}/estado")
    public Pedido cambiarEstado(@RequestHeader(value = HttpHeaders.AUTHORIZATION, required = false) String token,
                                @PathVariable Long id, @Valid @RequestBody CambiarEstadoRequest solicitud) {
        return servicio.cambiarEstado(jwt.autenticar(token), id, solicitud.estado());
    }

    @DeleteMapping("/{id}")
    @ResponseStatus(HttpStatus.NO_CONTENT)
    public void eliminar(@RequestHeader(value = HttpHeaders.AUTHORIZATION, required = false) String token,
                         @PathVariable Long id) {
        servicio.eliminar(jwt.autenticar(token), id);
    }
}
