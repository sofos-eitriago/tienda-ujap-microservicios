FROM nginx:1.27-alpine
# openssl crea el certificado HTTPS de desarrollo la primera vez que arranca (ver 15-certificado.sh)
RUN apk add --no-cache openssl
COPY nginx.conf /etc/nginx/nginx.conf
COPY --chmod=755 15-certificado.sh /docker-entrypoint.d/15-certificado.sh
EXPOSE 80 443
