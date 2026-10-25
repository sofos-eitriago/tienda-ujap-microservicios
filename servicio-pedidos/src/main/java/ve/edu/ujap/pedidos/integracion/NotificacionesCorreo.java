package ve.edu.ujap.pedidos.integracion;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.mail.MailException;
import org.springframework.mail.SimpleMailMessage;
import org.springframework.mail.javamail.JavaMailSenderImpl;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ResponseStatusException;
import ve.edu.ujap.pedidos.modelo.EstadoPedido;
import ve.edu.ujap.pedidos.modelo.Pedido;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.Map;
import java.util.concurrent.CompletableFuture;
import java.util.stream.Collectors;

/**
 * Avisa por correo al cliente cuando se crea su pedido y cada vez que cambia de estado.
 * En desarrollo los correos llegan al buzón de pruebas Mailpit; con SMTP_HOST, etc. salen a Internet.
 * Se envían en segundo plano: si el correo falla, el pedido igual se procesa.
 */
@Component
public class NotificacionesCorreo {

    private static final Logger log = LoggerFactory.getLogger(NotificacionesCorreo.class);
    private static final Map<EstadoPedido, String> FRASES = Map.of(
            EstadoPedido.ENVIADO, "ya va en camino",
            EstadoPedido.ENTREGADO, "fue entregado. ¡Gracias por tu compra!",
            EstadoPedido.CANCELADO, "fue cancelado y sus productos volvieron al catálogo",
            EstadoPedido.PENDIENTE, "volvió a quedar pendiente",
            EstadoPedido.RECHAZADO, "no se pudo completar por una falla interna; no se te cobró nada");

    private final JavaMailSenderImpl correo = new JavaMailSenderImpl();
    private final ServiciosExternos servicios;
    private final String remitente;

    public NotificacionesCorreo(ServiciosExternos servicios,
                                @Value("${correo.smtp.host}") String host,
                                @Value("${correo.smtp.puerto}") int puerto,
                                @Value("${correo.smtp.usuario}") String usuario,
                                @Value("${correo.smtp.clave}") String clave,
                                @Value("${correo.smtp.starttls}") boolean starttls,
                                @Value("${correo.remitente}") String remitente) {
        this.servicios = servicios;
        this.remitente = remitente;
        correo.setHost(host);
        correo.setPort(puerto);
        correo.setDefaultEncoding("UTF-8");
        var propiedades = correo.getJavaMailProperties();
        propiedades.put("mail.smtp.connectiontimeout", "5000");
        propiedades.put("mail.smtp.timeout", "5000");
        propiedades.put("mail.smtp.writetimeout", "5000");
        if (!usuario.isBlank()) { // sin usuario (Mailpit) no se autentica
            correo.setUsername(usuario);
            correo.setPassword(clave);
            propiedades.put("mail.smtp.auth", "true");
        }
        if (starttls) {
            propiedades.put("mail.smtp.starttls.enable", "true");
            propiedades.put("mail.smtp.starttls.required", "true");
        }
    }

    public void pedidoCreado(Pedido pedido) {
        enviar(pedido.getUsuarioId(), "Recibimos tu pedido #" + pedido.getId(),
                "Hola, " + pedido.getUsuarioNombre() + ":\n\n"
                        + "Recibimos tu pedido #" + pedido.getId() + " y apartamos sus productos:\n\n"
                        + detalle(pedido) + "\n\n"
                        + "Te escribiremos cuando cambie de estado.\n");
    }

    public void estadoCambiado(Pedido pedido) {
        enviar(pedido.getUsuarioId(), "Tu pedido #" + pedido.getId() + " está " + pedido.getEstado(),
                "Hola, " + pedido.getUsuarioNombre() + ":\n\n"
                        + "Tu pedido #" + pedido.getId() + " " + FRASES.getOrDefault(pedido.getEstado(), "cambió de estado") + ".\n\n"
                        + detalle(pedido) + "\n");
    }

    /** El texto se arma antes de pasar a segundo plano; el correo del cliente se consulta al enviar. */
    private void enviar(Long usuarioId, String asunto, String texto) {
        CompletableFuture.runAsync(() -> {
            try {
                SimpleMailMessage mensaje = new SimpleMailMessage();
                mensaje.setFrom(remitente);
                mensaje.setTo(servicios.obtenerUsuario(usuarioId).email());
                mensaje.setSubject(asunto);
                mensaje.setText(texto);
                correo.send(mensaje);
            } catch (MailException | ResponseStatusException e) {
                log.warn("No se pudo enviar el correo \"{}\" al usuario {}: {}", asunto, usuarioId, e.getMessage());
            }
        });
    }

    private static String detalle(Pedido pedido) {
        String lineas = pedido.getItems().stream()
                .map(i -> String.format("  %d × %s  %s", i.getCantidad(), i.getProductoNombre(), dolares(i.getSubtotal())))
                .collect(Collectors.joining("\n"));
        return lineas + "\n\n  Total: " + dolares(pedido.getTotal());
    }

    private static String dolares(BigDecimal monto) {
        return "$" + monto.setScale(2, RoundingMode.HALF_UP).toPlainString();
    }
}
