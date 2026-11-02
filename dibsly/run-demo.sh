#!/bin/sh
set -eu
cd "$(dirname "$0")"
export APP_ENV=development DEMO_MODE=true SECURE_COOKIES=false
export PORT="${PORT:-8092}" ADMIN_USERNAME="${ADMIN_USERNAME:-admin}" ADMIN_PASSWORD="${ADMIN_PASSWORD:-DibslyAdmin2026!}"
[ -f target/dibsly-1.0.0.jar ] || sh ./mvnw -f reactor/pom.xml package
exec java -Xms64m -Xmx256m -jar target/dibsly-1.0.0.jar
