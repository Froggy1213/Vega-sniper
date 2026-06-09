package postgres

import (
	"context"
	"fmt"
	"log/slog"
	"time"

	"github.com/jackc/pgx/v5/pgxpool"
)

type Repository struct {
	pool *pgxpool.Pool
}

func NewRepository(ctx context.Context, databaseURL string) (*Repository, error) {
	cfg, err := pgxpool.ParseConfig(databaseURL)
	if err != nil {
		return nil, fmt.Errorf("failed to parse database URL: %w", err)
	}

	// Настройка пула соединений
	cfg.MaxConns = 10           // Максимальное число соединений (3 воркера + запас)
	cfg.MinConns = 2            // Минимальное — всегда держим 2 прогретыми
	cfg.MaxConnLifetime = 1 * time.Hour   // Пересоздавать соединения каждый час
	cfg.MaxConnIdleTime = 5 * time.Minute // Закрывать idle-соединения через 5 мин
	cfg.HealthCheckPeriod = 30 * time.Second

	pool, err := pgxpool.NewWithConfig(ctx, cfg)
	if err != nil {
		return nil, fmt.Errorf("failed to connect to database: %w", err)
	}

	// Check the connection
	if err := pool.Ping(ctx); err != nil {
		pool.Close()
		return nil, fmt.Errorf("database unavailable (ping failed): %w", err)
	}

	// Automatically create the table for stored item IDs
	query := `
		CREATE TABLE IF NOT EXISTS mercari_parsed_items (
			id VARCHAR(255) PRIMARY KEY,
			created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
		);
	`
	_, err = pool.Exec(ctx, query)
	if err != nil {
		return nil, fmt.Errorf("failed to create table: %w", err)
	}

	slog.Info("✅ Successfully connected to PostgreSQL")

	return &Repository{pool: pool}, nil
}

func (r *Repository) Exists(ctx context.Context, itemID string) (bool, error) {
	var exists bool
	query := `SELECT EXISTS(SELECT 1 FROM mercari_parsed_items WHERE id=$1)`
	err := r.pool.QueryRow(ctx, query, itemID).Scan(&exists)
	return exists, err
}

func (r *Repository) Save(ctx context.Context, itemID string) error {
	query := `INSERT INTO mercari_parsed_items (id) VALUES ($1) ON CONFLICT (id) DO NOTHING`
	_, err := r.pool.Exec(ctx, query, itemID)
	return err
}

func (r *Repository) Close() {
	if r.pool != nil {
		r.pool.Close()
	}
}

func (r *Repository) GetActiveKeywords(ctx context.Context) ([]string, error) {
	query := `
		SELECT DISTINCT keyword 
		FROM searches 
		WHERE is_active = true AND platform = 'mercari'
	`

	rows, err := r.pool.Query(ctx, query)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var keywords []string
	for rows.Next() {
		var kw string
		if err := rows.Scan(&kw); err != nil {
			slog.Error("Ошибка чтения строки ключевого слова", "error", err)
			continue
		}
		keywords = append(keywords, kw)
	}

	return keywords, rows.Err()
}
