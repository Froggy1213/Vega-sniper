package main

import (
	"context"
	"fmt"
	"log/slog"
	"os"
	"os/signal"
	"strings"
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

	// run() возвращает ошибку — так все defer отрабатывают до os.Exit
	if err := run(); err != nil {
		slog.Error("Fatal error", "error", err)
		os.Exit(1)
	}
}

func run() error {
	// Context for graceful shutdown
	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stop()

	// 1. Инициализация БД
	dbURL := os.Getenv("DATABASE_URL")
	if dbURL == "" {
		return fmt.Errorf("DATABASE_URL is not set")
	}

	repo, err := postgres.NewRepository(ctx, dbURL)
	if err != nil {
		return fmt.Errorf("database: %w", err)
	}
	defer repo.Close()

	// 2. Инициализация RabbitMQ
	rabbitURL := os.Getenv("RABBITMQ_URL")
	if rabbitURL == "" {
		return fmt.Errorf("RABBITMQ_URL is not set")
	}

	pub, err := rabbitmq.NewPublisher(rabbitURL)
	if err != nil {
		return fmt.Errorf("rabbitmq: %w", err)
	}
	defer pub.Close()

	// 3. Прокси
	var proxyList []string
	proxiesEnv := os.Getenv("PROXIES")
	if proxiesEnv != "" {
		proxyList = strings.Split(proxiesEnv, ",")
		slog.Info("🌐 Loaded proxies", "count", len(proxyList))
	} else {
		slog.Warn("⚠️ No proxies configured — high risk of Mercari rate limiting")
	}

	mercariClient := mercari.NewClient(proxyList)

	// 4. Сборка и запуск бизнес-логики
	scraperApp := usecase.NewScraper(mercariClient, pub, repo)

	scraperApp.Start(ctx)

	slog.Info("✅ Microservice stopped safely.")
	return nil
}
