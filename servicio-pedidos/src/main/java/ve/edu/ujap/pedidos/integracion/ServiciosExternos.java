package ve.edu.ujap.pedidos.integracion;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.stereotype.Component;
import org.springframework.web.client.HttpClientErrorException;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientException;
import org.springframework.web.server.ResponseStatusException;
import ve.edu.ujap.pedidos.seguridad.ServicioJwt;

import java.time.Duration;
import java.util.Map;
import java.util.concurrent.CompletableFuture;

/**
 * Comunicación HTTP con los otros microservicios (cada petición lleva un token JWT de "servicio"):
 *  - usuarios  (Python/FastAPI)  → validar que el usuario existe
 *  - productos (Node.js/Express) → obtener precios, reservar y liberar stock
 *  - actividad (Go)              → registrar eventos
 */
@Component
public class ServiciosExternos {

    private static final Logger log = LoggerFactory.getLogger(ServiciosExternos.class);

    private final RestClient usuarios;
    private final RestClient productos;
    private final RestClient actividad;

    public ServiciosExternos(RestClient.Builder builder,
                             ServicioJwt jwt,
                             @Value("${servicios.usuarios.url}") String usuariosUrl,
                             @Value("${servicios.productos.url}") String productosUrl,
                             @Value("${servicios.actividad.url}") String actividadUrl) {
        var fabrica = new SimpleClientHttpRequestFactory();
        fabrica.setConnectTimeout(Duration.ofSeconds(3));
        fabrica.setReadTimeout(Duration.ofSeconds(5));

        RestClient.Builder base = builder.clone()
                .requestFactory(fabrica)
                .requestInterceptor((solicitud, cuerpo, ejecucion) -> {
                    solicitud.getHeaders().setBearerAuth(jwt.tokenServicio());
                    return ejecucion.execute(solicitud, cuerpo);
                });

        this.usuarios = base.clone().baseUrl(usuariosUrl).build();
        this.productos = base.clone().baseUrl(productosUrl).build();
        this.actividad = base.clone().baseUrl(actividadUrl).build();
    }

    public UsuarioRemoto obtenerUsuario(Long id) {
        try {
            return usuarios.get().uri("/api/usuarios/{id}", id).retrieve().body(UsuarioRemoto.class);
        } catch (HttpClientErrorException.NotFound e) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "El usuario " + id + " no existe");
        } catch (RestClientException e) {
            throw noDisponible("usuarios", e);
        }
    }

    public ProductoRemoto obtenerProducto(String id) {
        try {
            return productos.get().uri("/api/productos/{id}", id).retrieve().body(ProductoRemoto.class);
        } catch (HttpClientErrorException.NotFound e) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "El producto " + id + " no existe");
        } catch (RestClientException e) {
            throw noDisponible("productos", e);
        }
    }

    /** Descuenta stock. Idempotente: repetir la misma referencia no descuenta dos veces. */
    public void reservarStock(String productoId, int cantidad, String referencia) {
        moverStock("reservar", productoId, cantidad, referencia);
    }

    /** Devuelve stock reservado. Idempotente y seguro: si nunca se reservó, no hace nada. */
    public void liberarStock(String productoId, int cantidad, String referencia) {
        moverStock("liberar", productoId, cantidad, referencia);
    }

    private void moverStock(String operacion, String productoId, int cantidad, String referencia) {
        try {
            productos.post()
                    .uri("/api/productos/{id}/" + operacion, productoId)
                    .contentType(MediaType.APPLICATION_JSON)
                    .body(Map.of("cantidad", cantidad, "referencia", referencia))
                    .retrieve()
                    .toBodilessEntity();
        } catch (HttpClientErrorException.Conflict e) {
            throw new ResponseStatusException(HttpStatus.CONFLICT, detalle(e, "Stock insuficiente"));
        } catch (HttpClientErrorException.NotFound e) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "El producto " + productoId + " no existe");
        } catch (RestClientException e) {
            throw noDisponible("productos", e);
        }
    }

    /** Se envía en segundo plano: si el servicio de actividad falla, el pedido igual se procesa. */
    public void registrarEvento(String tipo, String mensaje, Map<String, Object> datos) {
        CompletableFuture.runAsync(() -> {
            try {
                actividad.post()
                        .uri("/api/eventos")
                        .contentType(MediaType.APPLICATION_JSON)
                        .body(Map.of("servicio", "pedidos", "tipo", tipo, "mensaje", mensaje, "datos", datos))
                        .retrieve()
                        .toBodilessEntity();
            } catch (RestClientException e) {
                log.warn("No se pudo registrar el evento en actividad: {}", e.getMessage());
            }
        });
    }

    private static ResponseStatusException noDisponible(String servicio, Exception e) {
        log.error("Error al comunicarse con el servicio de {}: {}", servicio, e.getMessage());
        return new ResponseStatusException(HttpStatus.SERVICE_UNAVAILABLE,
                "El servicio de " + servicio + " no está disponible en este momento");
    }

    /** Extrae el mensaje {"detail": "..."} que envían los otros servicios. */
    private static String detalle(HttpClientErrorException e, String porDefecto) {
        try {
            Map<?, ?> cuerpo = e.getResponseBodyAs(Map.class);
            if (cuerpo != null && cuerpo.get("detail") instanceof String texto) {
                return texto;
            }
        } catch (RuntimeException ignorada) {
            // cuerpo no legible: se usa el mensaje por defecto
        }
        return porDefecto;
    }
}
