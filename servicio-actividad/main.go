// Microservicio de Actividad — Go + net/http + driver oficial de MongoDB.
//
// Recibe los eventos que generan los demás microservicios (usuario creado, pedido creado,
// stock modificado...) y los guarda en MongoDB para mostrarlos como historial en tiempo real.
package main

import (
	"context"
	"encoding/json"
	"errors"
	"log"
	"net/http"
	"os"
	"slices"
	"strconv"
	"strings"
	"time"

	"github.com/golang-jwt/jwt/v5"
	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"
)

// Evento es una acción ocurrida en cualquier microservicio del sistema.
type Evento struct {
	ID       bson.ObjectID  `json:"id" bson:"_id"`
	Servicio string         `json:"servicio" bson:"servicio"`
	Tipo     string         `json:"tipo" bson:"tipo"`
	Mensaje  string         `json:"mensaje" bson:"mensaje"`
	Datos    map[string]any `json:"datos,omitempty" bson:"datos,omitempty"`
	Fecha    time.Time      `json:"fecha" bson:"fecha"`
}

// nuevoEvento es lo que se acepta en el cuerpo del POST (el id y la fecha los pone el servidor).
type nuevoEvento struct {
	Servicio string         `json:"servicio"`
	Tipo     string         `json:"tipo"`
	Mensaje  string         `json:"mensaje"`
	Datos    map[string]any `json:"datos"`
}

type conteoServicio struct {
	Servicio string `json:"servicio" bson:"_id"`
	Total    int    `json:"total" bson:"total"`
}

type servidor struct {
	eventos *mongo.Collection
	secreto []byte // secreto JWT compartido con los demás microservicios
}

func main() {
	mongoURL := entorno("MONGO_URL", "mongodb://localhost:27017")
	nombreBD := entorno("MONGO_DB", "tienda")
	puerto := entorno("PORT", "8080")
	secreto := entorno("JWT_SECRET", "secreto-de-desarrollo-cambiar-en-produccion-2026")
	if len(secreto) < 32 {
		log.Fatal("JWT_SECRET debe tener al menos 32 caracteres")
	}

	cliente, err := conectarMongo(mongoURL)
	if err != nil {
		log.Fatalf("No se pudo conectar a MongoDB: %v", err)
	}
	defer cliente.Disconnect(context.Background())

	s := &servidor{eventos: cliente.Database(nombreBD).Collection("eventos"), secreto: []byte(secreto)}

	mux := http.NewServeMux()
	mux.HandleFunc("GET /health", s.health)
	// Consultar el historial: solo administradores. Registrar eventos: solo otros microservicios.
	mux.HandleFunc("GET /api/eventos", s.requiereRol("admin")(s.listarEventos))
	mux.HandleFunc("POST /api/eventos", s.requiereRol("servicio")(s.crearEvento))
	mux.HandleFunc("GET /api/eventos/resumen", s.requiereRol("admin")(s.resumen))

	log.Printf("Servicio de actividad escuchando en el puerto %s", puerto)
	log.Fatal(http.ListenAndServe(":"+puerto, registrarPeticiones(mux)))
}

func conectarMongo(uri string) (*mongo.Client, error) {
	cliente, err := mongo.Connect(options.Client().ApplyURI(uri).SetServerSelectionTimeout(5 * time.Second))
	if err != nil {
		return nil, err
	}
	for intento := 1; intento <= 15; intento++ {
		ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
		err = cliente.Ping(ctx, nil)
		cancel()
		if err == nil {
			log.Println("Conectado a MongoDB")
			return cliente, nil
		}
		log.Printf("MongoDB no disponible (intento %d): %v", intento, err)
		time.Sleep(2 * time.Second)
	}
	return nil, err
}

func (s *servidor) health(w http.ResponseWriter, r *http.Request) {
	responderJSON(w, http.StatusOK, map[string]string{"status": "ok", "servicio": "actividad", "lenguaje": "Go"})
}

// GET /api/eventos?servicio=pedidos&limite=20
func (s *servidor) listarEventos(w http.ResponseWriter, r *http.Request) {
	filtro := bson.M{}
	if servicio := r.URL.Query().Get("servicio"); servicio != "" {
		filtro["servicio"] = servicio
	}
	limite := int64(50)
	if v, err := strconv.Atoi(r.URL.Query().Get("limite")); err == nil && v > 0 && v <= 500 {
		limite = int64(v)
	}

	ctx, cancel := context.WithTimeout(r.Context(), 5*time.Second)
	defer cancel()

	opciones := options.Find().SetSort(bson.D{{Key: "fecha", Value: -1}}).SetLimit(limite)
	cursor, err := s.eventos.Find(ctx, filtro, opciones)
	if err != nil {
		responderError(w, http.StatusInternalServerError, "Error al consultar los eventos")
		return
	}
	eventos := []Evento{}
	if err := cursor.All(ctx, &eventos); err != nil {
		responderError(w, http.StatusInternalServerError, "Error al leer los eventos")
		return
	}
	responderJSON(w, http.StatusOK, eventos)
}

// POST /api/eventos  {"servicio": "...", "tipo": "...", "mensaje": "...", "datos": {...}}
func (s *servidor) crearEvento(w http.ResponseWriter, r *http.Request) {
	var entrada nuevoEvento
	if err := json.NewDecoder(http.MaxBytesReader(w, r.Body, 1<<20)).Decode(&entrada); err != nil {
		responderError(w, http.StatusBadRequest, "El cuerpo de la petición no es un JSON válido")
		return
	}
	evento := Evento{
		ID:       bson.NewObjectID(),
		Servicio: strings.TrimSpace(entrada.Servicio),
		Tipo:     strings.TrimSpace(entrada.Tipo),
		Mensaje:  strings.TrimSpace(entrada.Mensaje),
		Datos:    entrada.Datos,
		Fecha:    time.Now().UTC(),
	}
	if evento.Servicio == "" || evento.Tipo == "" || evento.Mensaje == "" {
		responderError(w, http.StatusBadRequest, "Los campos servicio, tipo y mensaje son obligatorios")
		return
	}

	ctx, cancel := context.WithTimeout(r.Context(), 5*time.Second)
	defer cancel()
	if _, err := s.eventos.InsertOne(ctx, evento); err != nil {
		responderError(w, http.StatusInternalServerError, "No se pudo guardar el evento")
		return
	}
	responderJSON(w, http.StatusCreated, evento)
}

// GET /api/eventos/resumen → total de eventos y cantidad por microservicio (agregación de MongoDB)
func (s *servidor) resumen(w http.ResponseWriter, r *http.Request) {
	ctx, cancel := context.WithTimeout(r.Context(), 5*time.Second)
	defer cancel()

	pipeline := mongo.Pipeline{
		{{Key: "$group", Value: bson.D{{Key: "_id", Value: "$servicio"}, {Key: "total", Value: bson.D{{Key: "$sum", Value: 1}}}}}},
		{{Key: "$sort", Value: bson.D{{Key: "total", Value: -1}}}},
	}
	cursor, err := s.eventos.Aggregate(ctx, pipeline)
	if err != nil {
		responderError(w, http.StatusInternalServerError, "Error al calcular el resumen")
		return
	}
	porServicio := []conteoServicio{}
	if err := cursor.All(ctx, &porServicio); err != nil {
		responderError(w, http.StatusInternalServerError, "Error al leer el resumen")
		return
	}
	total := 0
	for _, c := range porServicio {
		total += c.Total
	}
	responderJSON(w, http.StatusOK, map[string]any{"total": total, "por_servicio": porServicio})
}

// requiereRol verifica el token JWT (firmado por el servicio de usuarios o por otro microservicio)
// y que su claim "rol" sea uno de los permitidos.
func (s *servidor) requiereRol(roles ...string) func(http.HandlerFunc) http.HandlerFunc {
	return func(siguiente http.HandlerFunc) http.HandlerFunc {
		return func(w http.ResponseWriter, r *http.Request) {
			token, ok := strings.CutPrefix(r.Header.Get("Authorization"), "Bearer ")
			if !ok || token == "" {
				responderError(w, http.StatusUnauthorized, "Falta el token de acceso (Authorization: Bearer <token>)")
				return
			}
			claims := jwt.MapClaims{}
			_, err := jwt.ParseWithClaims(token, claims, func(*jwt.Token) (any, error) { return s.secreto, nil },
				jwt.WithValidMethods([]string{"HS256"}))
			if errors.Is(err, jwt.ErrTokenExpired) {
				responderError(w, http.StatusUnauthorized, "El token expiró, inicia sesión de nuevo")
				return
			}
			if err != nil {
				responderError(w, http.StatusUnauthorized, "Token inválido")
				return
			}
			if rol, _ := claims["rol"].(string); !slices.Contains(roles, rol) {
				responderError(w, http.StatusForbidden, "No tienes permiso para esta operación")
				return
			}
			siguiente(w, r)
		}
	}
}

func responderJSON(w http.ResponseWriter, estado int, cuerpo any) {
	w.Header().Set("Content-Type", "application/json; charset=utf-8")
	w.WriteHeader(estado)
	json.NewEncoder(w).Encode(cuerpo)
}

// Mismo formato de error que los demás servicios: {"detail": "..."}
func responderError(w http.ResponseWriter, estado int, mensaje string) {
	responderJSON(w, estado, map[string]string{"detail": mensaje})
}

func registrarPeticiones(siguiente http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		inicio := time.Now()
		siguiente.ServeHTTP(w, r)
		if r.URL.Path != "/health" {
			log.Printf("%s %s (%v)", r.Method, r.URL.RequestURI(), time.Since(inicio).Round(time.Millisecond))
		}
	})
}

func entorno(clave, porDefecto string) string {
	if valor := os.Getenv(clave); valor != "" {
		return valor
	}
	return porDefecto
}
