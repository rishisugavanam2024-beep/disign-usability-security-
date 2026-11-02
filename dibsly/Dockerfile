FROM maven:3.9.11-eclipse-temurin-21 AS build
WORKDIR /build
COPY pom.xml .
COPY src ./src
COPY reactor ./reactor
RUN mvn -B --no-transfer-progress -f reactor/pom.xml verify

FROM eclipse-temurin:21-jre
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/* \
    && useradd --system --create-home --uid 10001 dibsly
WORKDIR /app
COPY --from=build /build/target/dibsly-1.0.0.jar /app/dibsly.jar
RUN mkdir /app/data && chown -R dibsly:dibsly /app
USER dibsly
EXPOSE 8090
HEALTHCHECK --interval=30s --timeout=5s --start-period=45s --retries=3 CMD curl --fail --silent http://127.0.0.1:8090/health || exit 1
ENTRYPOINT ["java","-XX:MaxRAMPercentage=65","-Duser.timezone=UTC","-jar","/app/dibsly.jar"]
