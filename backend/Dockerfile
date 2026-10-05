# ECHO backend (Spring Boot 4, Java 17). Multi-stage: Maven build -> slim JRE runtime.
FROM maven:3.9-eclipse-temurin-17 AS build
WORKDIR /src
COPY pom.xml .
RUN mvn -q -B dependency:go-offline
COPY src ./src
RUN mvn -q -B -DskipTests package && cp target/echo-backend-*.jar /app.jar

FROM eclipse-temurin:17-jre
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 10001 echo
COPY --from=build /app.jar /app/app.jar
USER echo
EXPOSE 8080
HEALTHCHECK --interval=15s --timeout=5s --start-period=40s --retries=8 CMD curl -fs http://localhost:8080/actuator/health || exit 1
ENTRYPOINT ["java", "-XX:MaxRAMPercentage=75", "-jar", "/app/app.jar"]
