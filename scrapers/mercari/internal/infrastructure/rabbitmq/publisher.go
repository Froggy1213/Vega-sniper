package rabbitmq

import (
	"context"
	"encoding/json"
	"fmt"
	"log/slog"
	"time"

	"mercari/internal/domain" // Убедись, что имя модуля совпадает с твоим go.mod

	amqp "github.com/rabbitmq/amqp091-go"
)

type Publisher struct {
	conn *amqp.Connection
	ch   *amqp.Channel
	q    amqp.Queue
}

// NewPublisher создает соединение с ретраями.
func NewPublisher(url string) (*Publisher, error) {
	var conn *amqp.Connection
	var err error

	for i := 1; i <= 7; i++ {
		conn, err = amqp.Dial(url)
		if err == nil {
			slog.Info("✅ Connected to RabbitMQ")
			break
		}
		slog.Warn(fmt.Sprintf("⏳ RabbitMQ unavailable (attempt %d/7)", i), "error", err)
		time.Sleep(3 * time.Second)
	}

	if err != nil {
		return nil, fmt.Errorf("failed to connect to RabbitMQ: %w", err)
	}

	ch, err := conn.Channel()
	if err != nil {
		return nil, fmt.Errorf("failed to create channel: %w", err)
	}

	q, err := ch.QueueDeclare("new_items_queue", true, false, false, false, nil)
	if err != nil {
		return nil, fmt.Errorf("failed to declare queue: %w", err)
	}

	return &Publisher{
		conn: conn,
		ch:   ch,
		q:    q,
	}, nil
}

// Publish реализует интерфейс domain.Publisher
func (p *Publisher) Publish(ctx context.Context, item domain.Item) error {
	msgBytes, err := json.Marshal(item)
	if err != nil {
		return err
	}

	err = p.ch.PublishWithContext(ctx, "", p.q.Name, false, false, amqp.Publishing{
		ContentType: "application/json",
		Body:        msgBytes,
	})

	if err == nil {
		slog.Info("📬 Sent to queue", "item", item.Name, "price", item.Price)
	}
	return err
}

func (p *Publisher) Close() error {
	if p.ch != nil {
		p.ch.Close()
	}
	if p.conn != nil {
		return p.conn.Close()
	}
	return nil
}
