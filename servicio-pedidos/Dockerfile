# Etapa 1: compilar con Maven
FROM maven:3.9-eclipse-temurin-21 AS build
WORKDIR /src

# Primero solo el pom.xml: las dependencias quedan en caché si no cambian
COPY pom.xml .
RUN mvn -B -q dependency:go-offline

COPY src ./src
RUN mvn -B -q package -DskipTests

# Etapa 2: imagen final solo con el JRE y el .jar
FROM eclipse-temurin:21-jre-alpine
WORKDIR /app
COPY --from=build /src/target/servicio-pedidos.jar app.jar
EXPOSE 8080
ENTRYPOINT ["java", "-jar", "app.jar"]
