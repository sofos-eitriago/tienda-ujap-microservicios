package ve.edu.ujap.pedidos.integracion;

// Respuesta de GET /api/usuarios/{id} del servicio de usuarios (Python)
public record UsuarioRemoto(Long id, String nombre, String email) {
}
