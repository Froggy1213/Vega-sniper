package domain

import (
	"context"
	"errors"
)

// ErrRateLimited возвращается шлюзом (gateway) когда внешний API отвечает 429.
var ErrRateLimited = errors.New("mercari rate limited")

// ScraperGateway - интерфейс для получения товаров (пока реализован только Mercari).
type ScraperGateway interface {
	SearchItems(ctx context.Context, condition SearchCondition) ([]Item, error)
}

// Publisher - интерфейс для отправки найденных товаров (реализация - RabbitMQ).
type Publisher interface {
	Publish(ctx context.Context, item Item) error
	Close() error // Для корректного закрытия соединения
}

// Интерфейс для работы с базой данных
type ItemRepository interface {
	Exists(ctx context.Context, itemID string) (bool, error)
	Save(ctx context.Context, itemID string) error
	GetActiveKeywords(ctx context.Context) ([]string, error)
	DeleteOlderThan(ctx context.Context, ageDays int) (int64, error)
	Close()
}
