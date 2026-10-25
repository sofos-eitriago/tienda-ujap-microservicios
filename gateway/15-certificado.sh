#!/bin/sh
# Se ejecuta al arrancar el contenedor (la imagen de Nginx corre todo lo que está en /docker-entrypoint.d/).
#
# 1) La primera vez crea el certificado HTTPS de desarrollo y lo guarda en el volumen "certificados":
#    - una autoridad certificadora (CA) local que SOLO puede firmar tienda.ujap.test, localhost y
#      127.0.0.1 (nameConstraints). Su clave privada se borra después de firmar: aunque alguien
#      copie el volumen, no puede usarla para falsificar otros sitios;
#    - el certificado del gateway, firmado por esa CA.
#    Si se importa ca.crt en Windows (configurar-dominio.ps1), el navegador muestra el candado sin avisos.
# 2) Escribe en qué puerto escucha HTTPS en la máquina, para que la redirección desde HTTP sea correcta.
set -eu

DIR=/etc/nginx/certificados
mkdir -p "$DIR"

if [ ! -f "$DIR/tienda.crt" ] || [ ! -f "$DIR/tienda.key" ] || ! openssl x509 -checkend 86400 -noout -in "$DIR/tienda.crt" >/dev/null; then
  echo "Creando el certificado HTTPS de desarrollo para tienda.ujap.test"
  TMP=$(mktemp -d)

  openssl req -x509 -newkey rsa:2048 -sha256 -days 825 -nodes -keyout "$TMP/ca.key" -out "$DIR/ca.crt" \
    -subj "/O=Tienda UJAP/CN=Tienda UJAP - CA local de desarrollo" \
    -addext "basicConstraints=critical,CA:TRUE,pathlen:0" \
    -addext "keyUsage=critical,keyCertSign,cRLSign" \
    -addext "nameConstraints=critical,permitted;DNS:tienda.ujap.test,permitted;DNS:localhost,permitted;IP:127.0.0.1/255.255.255.255" 2>/dev/null

  openssl req -newkey rsa:2048 -sha256 -nodes -keyout "$DIR/tienda.key" -out "$TMP/tienda.csr" -subj "/CN=tienda.ujap.test" 2>/dev/null
  cat > "$TMP/extensiones.cnf" <<EOF
basicConstraints=critical,CA:FALSE
keyUsage=critical,digitalSignature,keyEncipherment
extendedKeyUsage=serverAuth
subjectAltName=DNS:tienda.ujap.test,DNS:localhost,IP:127.0.0.1
EOF
  openssl x509 -req -in "$TMP/tienda.csr" -CA "$DIR/ca.crt" -CAkey "$TMP/ca.key" -set_serial "0x$(openssl rand -hex 16)" \
    -days 820 -sha256 -extfile "$TMP/extensiones.cnf" -out "$DIR/tienda.crt" 2>/dev/null

  rm -rf "$TMP"  # incluye ca.key: la CA no podrá firmar nada más
  chmod 600 "$DIR/tienda.key"
fi

# Si HTTPS no está en el 443 de la máquina, la redirección debe incluir el puerto (p. ej. :8443)
PUERTO="${PUERTO_HTTPS:-443}"
if [ "$PUERTO" = "443" ]; then SUFIJO=""; else SUFIJO=":$PUERTO"; fi
echo "set \$puerto_https \"$SUFIJO\";" > /etc/nginx/puerto-https.conf
