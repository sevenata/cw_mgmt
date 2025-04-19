#!/bin/bash

# Укажите свои учетные данные и название контейнера
USERNAME="ubuntu"
IP="85.202.192.86"
BACKEND_CONTAINER_PATTERN="frappe_docker-backend-1"  # Замените на реальный паттерн

# Подключаемся к серверу и выполняем команды
ssh -T $USERNAME@$IP << EOL
set -e

# Передаем паттерн поиска во внутреннюю среду
export CONTAINER_PATTERN="$BACKEND_CONTAINER_PATTERN"

# Находим полное имя контейнера с точным поиском
CONTAINER_NAME=\$(docker ps --format "{{.Names}}" | grep "\$CONTAINER_PATTERN" | head -n1)

if [ -z "\$CONTAINER_NAME" ]; then
    echo "Error: Container with pattern '\$CONTAINER_PATTERN' not found!"
    docker ps --format "{{.Names}}" >&2
    exit 1
fi

echo "Found container: \$CONTAINER_NAME"

# Выполняем команды внутри контейнера
docker exec \$CONTAINER_NAME sh -c "cd apps/car_wash_management &&
    git pull origin main --no-rebase &&
    bench --site beta.jyy.kz migrate"

#bench --site erpdev.juu.kz migrate

# Перезапускаем контейнер
docker restart \$CONTAINER_NAME
echo "Container \$CONTAINER_NAME has been updated and restarted successfully."
EOL
