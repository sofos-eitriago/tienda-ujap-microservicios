# Etapa 1: compilar el binario
FROM golang:1.25-alpine AS build
WORKDIR /src

COPY go.mod go.sum ./
RUN go mod download

COPY *.go ./
RUN CGO_ENABLED=0 go build -ldflags="-s -w" -o /actividad .

# Etapa 2: imagen final pequeña (solo el binario)
FROM alpine:3.20
WORKDIR /app
COPY --from=build /actividad ./actividad
USER nobody
EXPOSE 8080
CMD ["./actividad"]
