package usecase

import (
	"context"
	"log/slog"
	"math/rand"
	"sync"
	"time"

	"mercari/internal/domain"
)

const searchTimeout = 30 * time.Second // Таймаут одного HTTP-запроса к Mercari

type Scraper struct {
	gateway   domain.ScraperGateway
	publisher domain.Publisher
	repo      domain.ItemRepository
}

func NewScraper(gw domain.ScraperGateway, pub domain.Publisher, repo domain.ItemRepository) *Scraper {
	return &Scraper{
		gateway:   gw,
		publisher: pub,
		repo:      repo,
	}
}

// Start запускает планировщик и рабочих.
func (s *Scraper) Start(ctx context.Context) {
	const numWorkers = 3 // Количество одновременных рабочих (горутин)

	jobs := make(chan string, 100)
	var wg sync.WaitGroup

	// 1. Запускаем рабочих в фоне
	for i := 1; i <= numWorkers; i++ {
		wg.Add(1)
		go s.worker(ctx, i, jobs, &wg)
	}

	// 2. Планировщик раз в 30 секунд забирает слова из БД и кидает их в канал
	ticker := time.NewTicker(30 * time.Second)
	defer ticker.Stop()

	// Выполняем первую раздачу задач сразу при старте
	s.dispatchJobs(ctx, jobs)

	for {
		select {
		case <-ctx.Done():
			slog.Info("🛑 Shutdown signal received. Draining job queue...")
			close(jobs)      // Закрываем канал — воркеры доедят оставшиеся задачи
			wg.Wait()         // Ждём завершения всех in-flight операций
			slog.Info("🛑 All workers finished. Scraper stopped cleanly.")
			return
		case <-ticker.C:
			s.dispatchJobs(ctx, jobs)
		}
	}
}

// dispatchJobs достает уникальные запросы из базы и кладет их в очередь (канал)
func (s *Scraper) dispatchJobs(ctx context.Context, jobs chan<- string) {
	keywords, err := s.repo.GetActiveKeywords(ctx)
	if err != nil {
		slog.Error("⚠️ Failed to get active keywords from DB", "error", err)
		return
	}

	if len(keywords) == 0 {
		slog.Info("📭 No active search queries in DB yet")
		return
	}

	slog.Info("📋 Found active queries, dispatching to workers", "count", len(keywords))

	// Раздаем задачи воркерам
	for _, kw := range keywords {
		select {
		case jobs <- kw: // Пытаемся положить задачу в канал
		case <-ctx.Done():
			return
		}
	}
}

// worker - это рабочий поток, который бесконечно ждет задачи из канала jobs
func (s *Scraper) worker(ctx context.Context, id int, jobs <-chan string, wg *sync.WaitGroup) {
	defer wg.Done()
	slog.Info("👷 Worker started", "worker_id", id)

	for keyword := range jobs {
		// Используем отдельный контекст с таймаутом, чтобы shutdown не обрывал
		// текущий HTTP-запрос на полуслове (но при этом не висим вечно)
		searchCtx, cancel := context.WithTimeout(context.Background(), searchTimeout)
		s.processSearch(searchCtx, id, domain.SearchCondition{Keyword: keyword})
		cancel()

		// ⏱ ВАЖНО: Умная случайная задержка (Jitter) от 2 до 6 секунд
		// Имитирует поведение человека и защищает от бана Mercari
		jitter := time.Duration(rand.Intn(4000)+2000) * time.Millisecond
		time.Sleep(jitter)
	}

	slog.Info("🛑 Worker stopped (job queue closed)", "worker_id", id)
}

// processSearch выполняет сам процесс поиска и отправки для одного ключевого слова
func (s *Scraper) processSearch(ctx context.Context, workerID int, cond domain.SearchCondition) {
	slog.Info("🔍 Searching for new items...", "worker_id", workerID, "keyword", cond.Keyword)

	items, err := s.gateway.SearchItems(ctx, cond)
	if err != nil {
		slog.Error("⚠️ Failed to retrieve items", "worker_id", workerID, "keyword", cond.Keyword, "error", err)
		return
	}

	newItemsCount := 0
	for _, item := range items {
		// 1. Проверяем в БД, отправляли ли мы уже этот товар
		exists, err := s.repo.Exists(ctx, item.ID)
		if err != nil {
			slog.Error("Database check error", "error", err)
			continue
		}
		if exists {
			continue // Товар уже был, пропускаем
		}

		// 2. Отправляем в RabbitMQ
		err = s.publisher.Publish(ctx, item)
		if err != nil {
			slog.Error("❌ Failed to send to RabbitMQ", "error", err)
			continue
		}

		// 3. Сохраняем ID в БД
		err = s.repo.Save(ctx, item.ID)
		if err != nil {
			slog.Error("Database save error", "error", err)
		} else {
			newItemsCount++
		}
	}

	if newItemsCount > 0 {
		slog.Info("✅ Found new items!", "worker_id", workerID, "keyword", cond.Keyword, "count", newItemsCount)
	} else {
		slog.Info("🤷 No new items found.", "worker_id", workerID, "keyword", cond.Keyword)
	}
}
