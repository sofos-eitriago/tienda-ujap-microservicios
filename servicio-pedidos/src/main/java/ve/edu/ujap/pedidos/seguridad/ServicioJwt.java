package ve.edu.ujap.pedidos.seguridad;

import io.jsonwebtoken.Claims;
import io.jsonwebtoken.ExpiredJwtException;
import io.jsonwebtoken.JwtException;
import io.jsonwebtoken.Jwts;
import io.jsonwebtoken.security.Keys;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ResponseStatusException;

import javax.crypto.SecretKey;
import java.nio.charset.StandardCharsets;
import java.time.Instant;
import java.util.Date;

/**
 * Tokens JWT (HS256) con el secreto compartido por los 4 microservicios.
 *  - Verifica los tokens de los usuarios (emitidos por el servicio de usuarios).
 *  - Firma tokens cortos de "servicio" para llamar a los otros microservicios.
 */
@Component
public class ServicioJwt {

    private final SecretKey clave;

    public ServicioJwt(@Value("${jwt.secret}") String secreto) {
        if (secreto.length() < 32) {
            throw new IllegalStateException("JWT_SECRET debe tener al menos 32 caracteres");
        }
        this.clave = Keys.hmacShaKeyFor(secreto.getBytes(StandardCharsets.UTF_8));
    }

    /** Lee el header "Authorization: Bearer ..." y devuelve la identidad, o responde 401. */
    public Identidad autenticar(String header) {
        if (header == null || !header.startsWith("Bearer ")) {
            throw new ResponseStatusException(HttpStatus.UNAUTHORIZED, "Falta el token de acceso (Authorization: Bearer <token>)");
        }
        try {
            Claims claims = Jwts.parser().verifyWith(clave).build()
                    .parseSignedClaims(header.substring(7)).getPayload();
            String rol = claims.get("rol", String.class);
            if (claims.getSubject() == null || rol == null) {
                throw new ResponseStatusException(HttpStatus.UNAUTHORIZED, "Token inválido");
            }
            return new Identidad(claims.getSubject(), rol, claims.get("nombre", String.class));
        } catch (ExpiredJwtException e) {
            throw new ResponseStatusException(HttpStatus.UNAUTHORIZED, "El token expiró, inicia sesión de nuevo");
        } catch (JwtException | IllegalArgumentException e) {
            throw new ResponseStatusException(HttpStatus.UNAUTHORIZED, "Token inválido");
        }
    }

    public String tokenServicio() {
        Instant ahora = Instant.now();
        return Jwts.builder()
                .subject("servicio-pedidos")
                .claim("rol", "servicio")
                .issuedAt(Date.from(ahora))
                .expiration(Date.from(ahora.plusSeconds(300)))
                // HS256 explícito: con una clave larga jjwt elegiría HS384/HS512 y los demás servicios lo rechazarían
                .signWith(clave, Jwts.SIG.HS256)
                .compact();
    }
}
