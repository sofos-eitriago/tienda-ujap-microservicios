package ve.edu.ujap.pedidos.seguridad;

/** Quién hace la petición, según su token JWT. */
public record Identidad(String sub, String rol, String nombre) {

    public boolean esAdmin() {
        return "admin".equals(rol);
    }

    /** Id del usuario (null si el token es de un microservicio). */
    public Long usuarioId() {
        return sub != null && sub.chars().allMatch(Character::isDigit) && !sub.isEmpty() ? Long.valueOf(sub) : null;
    }
}
