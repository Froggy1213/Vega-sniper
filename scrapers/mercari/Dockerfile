# Этап 1: Сборка (Используем образ с установленным Go)
FROM golang:1.26-alpine AS builder

WORKDIR /app

# Копируем файлы модулей и скачиваем зависимости
COPY go.mod go.sum ./
RUN go mod download

# Копируем исходный код
COPY . .

# Компилируем бинарник (CGO_ENABLED=0 делает его максимально независимым)
RUN CGO_ENABLED=0 GOOS=linux go build -o mercari-scraper-v2 ./cmd/scraper/main.go

# Этап 2: Финальный образ (Используем пустой alpine linux)
FROM alpine:latest

# Добавляем корневые сертификаты, чтобы Go мог делать HTTPS запросы к Mercari
RUN apk --no-cache add ca-certificates

WORKDIR /root/

# Копируем только готовый бинарник из первого этапа
COPY --from=builder /app/mercari-scraper-v2 .

# Запускаем парсер
CMD ["./mercari-scraper-v2"]