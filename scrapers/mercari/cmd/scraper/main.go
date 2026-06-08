package main

import (
	"context"
	"log/slog"
	"os"
	"os/signal"
	"syscall"

	"mercari/internal/infrastructure/mercari"
	"mercari/internal/infrastructure/postgres"
	"mercari/internal/infrastructure/rabbitmq"
	"mercari/internal/usecase"
)

func main() {
	logger := slog.New(slog.NewJSONHandler(os.Stdout, nil))
	slog.SetDefault(logger)

	slog.Info("🚀 Starting Mercari scraper microservice")

	// Context for start and shutdown
	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stop()

	// 1. Инициализация БД
	dbURL := os.Getenv("DATABASE_URL")
	if dbURL == "" {
		// Локальный фолбэк (подставь свои данные, если запускаешь без докера)
		dbURL = "postgres://sniffer_admin:super_secret_password@localhost:5432/sniffer_db"
	}

	repo, err := postgres.NewRepository(ctx, dbURL)
	if err != nil {
		slog.Error("Critical DB error", "error", err)
		os.Exit(1)
	}
	defer repo.Close()

	// 2. Инициализация RabbitMQ
	rabbitURL := os.Getenv("RABBITMQ_URL")
	if rabbitURL == "" {
		rabbitURL = "amqp://guest:guest@localhost:5672/"
	}

	pub, err := rabbitmq.NewPublisher(rabbitURL)
	if err != nil {
		slog.Error("Critical RabbitMQ error", "error", err)
		os.Exit(1)
	}
	defer pub.Close()

	var proxyList []string
	proxiesEnv := os.Getenv("PROXIES")
	if proxiesEnv != "" {
		proxyList = strings.Split(proxiesEnv, ",")
		slog.Info("🌐 Загружены прокси", "count", len(proxyList))
	} else {
		slog.Warn("⚠️ Запуск без прокси. Есть высокий риск блокировки от Mercari!")
	}

	mercariClient := mercari.NewClient(proxyList)

	// 4. Сборка и запуск бизнес-логики
	scraperApp := usecase.NewScraper(mercariClient, pub, repo)

	scraperApp.Start(ctx)

	slog.Info("✅ Microservice stopped safely and successfully.")
}
