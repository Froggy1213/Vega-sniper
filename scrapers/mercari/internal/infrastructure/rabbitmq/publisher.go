package rabbitmq

import (
	"context"
	"encoding/json"
	"fmt"
	"log/slog"
	"sync"
	"time"

	"mercari/internal/domain"

	amqp "github.com/rabbitmq/amqp091-go"
)

const (
	queueName       = "new_items_queue"
	dlxName         = "dead_letter_exchange"
	dlqName         = "dead_letter_queue"
	dlRoutingKey    = "dead"
	maxReconnects   = 7
	reconnectDelay  = 3 * time.Second
	publishRetries  = 3
	publishDelay    = 1 * time.Second
)

type Publisher struct {
	url  string
	mu   sync.Mutex
	conn *amqp.Connection
	ch   *amqp.Channel
	q    amqp.Queue
}

// NewPublisher создает соединение с ретраями и сохраняет URL для авто-переподключения.
func NewPublisher(url string) (*Publisher, error) {
	p := &Publisher{url: url}
	if err := p.connect(); err != nil {
		return nil, err
	}
	return p, nil
}

// connect устанавливает соединение, канал и объявляет очередь.
func (p *Publisher) connect() error {
	var conn *amqp.Connection
	var err error

	for i := 1; i <= maxReconnects; i++ {
		conn, err = amqp.Dial(p.url)
		if err == nil {
			slog.Info("✅ Connected to RabbitMQ")
			break
		}
		slog.Warn(fmt.Sprintf("⏳ RabbitMQ unavailable (attempt %d/%d)", i, maxReconnects), "error", err)
		time.Sleep(reconnectDelay)
	}

	if err != nil {
		return fmt.Errorf("failed to connect to RabbitMQ after %d attempts: %w", maxReconnects, err)
	}

	ch, err := conn.Channel()
	if err != nil {
		conn.Close()
		return fmt.Errorf("failed to create channel: %w", err)
	}

	// Declare dead-letter exchange and queue for failed messages
	if err := ch.ExchangeDeclare(dlxName, "direct", true, false, false, false, nil); err != nil {
		ch.Close()
		conn.Close()
		return fmt.Errorf("failed to declare dead-letter exchange: %w", err)
	}
	if _, err := ch.QueueDeclare(dlqName, true, false, false, false, nil); err != nil {
		ch.Close()
		conn.Close()
		return fmt.Errorf("failed to declare dead-letter queue: %w", err)
	}
	if err := ch.QueueBind(dlqName, dlRoutingKey, dlxName, false, nil); err != nil {
		ch.Close()
		conn.Close()
		return fmt.Errorf("failed to bind dead-letter queue: %w", err)
	}

	q, err := ch.QueueDeclare(queueName, true, false, false, false, amqp.Table{
		"x-dead-letter-exchange": dlxName,
		"x-dead-letter-routing-key": dlRoutingKey,
	})
	if err != nil {
		ch.Close()
		conn.Close()
		return fmt.Errorf("failed to declare queue: %w", err)
	}

	// Close old resources before swapping (safe — may be nil on first call)
	p.closeResources()

	p.conn = conn
	p.ch = ch
	p.q = q

	return nil
}

// closeResources silently closes channel and connection if they exist.
func (p *Publisher) closeResources() {
	if p.ch != nil {
		p.ch.Close()
		p.ch = nil
	}
	if p.conn != nil {
		p.conn.Close()
		p.conn = nil
	}
}

// Publish реализует интерфейс domain.Publisher с авто-переподключением.
func (p *Publisher) Publish(ctx context.Context, item domain.Item) error {
	msgBytes, err := json.Marshal(item)
	if err != nil {
		return fmt.Errorf("marshal item: %w", err)
	}

	p.mu.Lock()
	defer p.mu.Unlock()

	for attempt := 1; attempt <= publishRetries; attempt++ {
		// If we don't have a channel, try to reconnect
		if p.ch == nil {
			if err := p.connect(); err != nil {
				slog.Error("Reconnect failed, will retry", "attempt", attempt, "error", err)
				time.Sleep(publishDelay)
				continue
			}
		}

		err = p.ch.PublishWithContext(ctx, "", p.q.Name, false, false, amqp.Publishing{
			ContentType: "application/json",
			Body:        msgBytes,
		})

		if err == nil {
			slog.Info("📬 Sent to queue", "item", item.Name, "price", item.Price)
			return nil
		}

		// Publish failed — likely connection lost. Reset and reconnect.
		slog.Warn("Publish failed, reconnecting", "attempt", attempt, "error", err)
		p.closeResources()

		if err := p.connect(); err != nil {
			slog.Error("Reconnect failed", "attempt", attempt, "error", err)
			continue
		}
	}

	return fmt.Errorf("failed to publish after %d attempts", publishRetries)
}

func (p *Publisher) Close() error {
	p.mu.Lock()
	defer p.mu.Unlock()
	p.closeResources()
	return nil
}
