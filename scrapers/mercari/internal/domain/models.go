package domain

// Item - структура товара, которую ожидает наш Python-бот.
// Обрати внимание: мы используем теги json, так как эта структура будет уходить в RabbitMQ.
type Item struct {
	Platform string `json:"platform"`
	ID       string `json:"id"`
	Name     string `json:"name"`
	Price    int    `json:"price"`
	URL      string `json:"url"`
	PhotoURL string `json:"photo_url"`
}

// SearchCondition - параметры поиска.
type SearchCondition struct {
	Keyword string
}
