package main

import (
	"context"
	"crypto/ecdsa"
	"crypto/elliptic"
	"crypto/rand"
	"encoding/base64"
	"encoding/json"
	"fmt"
	"log"
	"os"
	"strconv"
	"time"

	"github.com/golang-jwt/jwt/v5"
	"github.com/google/uuid"
	"github.com/imroc/req/v3"
	amqp "github.com/rabbitmq/amqp091-go"
)

// --- Структуры для API Mercari ---
type SearchCondition struct {
	Keyword string   `json:"keyword"`
	Sort    string   `json:"sort"`
	Order   string   `json:"order"`
	Status  []string `json:"status"`
}

type SearchPayload struct {
	PageSize        int             `json:"pageSize"`
	SearchSessionId string          `json:"searchSessionId"`
	SearchCondition SearchCondition `json:"searchCondition"`
}

type MercariResponse struct {
	Items []MercariItem `json:"items"`
}

type MercariItem struct {
	ID     string  `json:"id"`
	Name   string  `json:"name"`
	Price  string  `json:"price"` // Mercari отдает цену как строку
	Photos []Photo `json:"photos"`
}

type Photo struct {
	URI string `json:"uri"`
}

// --- Структура, которую ждет наш Python-бот ---
type ProductMessage struct {
	Platform string `json:"platform"`
	ID       string `json:"id"`
	Name     string `json:"name"`
	Price    int    `json:"price"` // Бот ждет число (int)
	URL      string `json:"url"`
	PhotoURL string `json:"photo_url"` // Бот ждет photo_url
}

// --- DPoP Токен ---
func generateMercariDPoP(method, url string) (string, error) {
	privateKey, err := ecdsa.GenerateKey(elliptic.P256(), rand.Reader)
	if err != nil {
		return "", err
	}
	pubKey := privateKey.PublicKey
	xBase64 := base64.RawURLEncoding.EncodeToString(pubKey.X.Bytes())
	yBase64 := base64.RawURLEncoding.EncodeToString(pubKey.Y.Bytes())

	token := jwt.NewWithClaims(jwt.SigningMethodES256, jwt.MapClaims{
		"iat":  time.Now().Unix(),
		"jti":  uuid.New().String(),
		"htm":  method,
		"htu":  url,
		"uuid": uuid.New().String(),
	})
	token.Header["typ"] = "dpop+jwt"
	token.Header["jwk"] = map[string]string{"kty": "EC", "crv": "P-256", "x": xBase64, "y": yBase64}

	return token.SignedString(privateKey)
}

func main() {
	fmt.Println("🚀 Запускаем боевой микросервис парсера Mercari...")

	// 1. Подключаемся к RabbitMQ через переменную окружения (чтобы работало в Docker)
	rabbitURL := os.Getenv("RABBITMQ_URL")
	if rabbitURL == "" {
		rabbitURL = "amqp://guest:guest@localhost:5672/" // Фолбэк для тестов без докера
	}

	var conn *amqp.Connection
	var err error

	// Делаем 7 попыток с интервалом в 3 секунды
	for i := 1; i <= 7; i++ {
		conn, err = amqp.Dial(rabbitURL)
		if err == nil {
			fmt.Println("✅ Успешно подключились к RabbitMQ!")
			break // Выходим из цикла, если подключение удалось
		}
		log.Printf("⏳ RabbitMQ еще не готов, ждем... (попытка %d/7): %v\n", i, err)
		time.Sleep(3 * time.Second)
	}

	if err != nil {
		log.Fatalf("❌ Ошибка подключения к RabbitMQ после всех попыток: %v", err)
	}
	defer conn.Close()

	ch, err := conn.Channel()
	if err != nil {
		log.Fatalf("❌ Ошибка создания канала: %v", err)
	}
	defer ch.Close()

	// 2. Создаем очередь
	q, err := ch.QueueDeclare("new_items_queue", true, false, false, false, nil)
	if err != nil {
		log.Fatalf("❌ Ошибка создания очереди: %v", err)
	}

	// 3. Настраиваем HTTP-клиент
	client := req.C().ImpersonateChrome().SetTimeout(10 * time.Second)
	targetURL := "https://api.mercari.jp/v2/entities:search"

	// Локальный кэш
	seenItems := make(map[string]bool)

	// 4. Запускаем БЕСКОНЕЧНЫЙ ЦИКЛ
	for {
		fmt.Println("\n🔍 Ищем новые товары...")

		dpopToken, _ := generateMercariDPoP("POST", targetURL)
		payload := SearchPayload{
			PageSize:        10,
			SearchSessionId: uuid.New().String(),
			SearchCondition: SearchCondition{
				Keyword: "Pokemon", // Пока захардкожено, потом научим брать из базы!
				Sort:    "SORT_CREATED_TIME",
				Order:   "ORDER_DESC",
				Status:  []string{"STATUS_ON_SALE"},
			},
		}

		var result MercariResponse
		resp, err := client.R().
			SetHeader("X-Platform", "web").
			SetHeader("Accept", "application/json").
			SetHeader("DPoP", dpopToken).
			SetBody(&payload).
			SetSuccessResult(&result).
			Post(targetURL)

		if err != nil || !resp.IsSuccessState() {
			log.Println("⚠️ Ошибка сети или API. Ждем и пробуем снова...")
			time.Sleep(15 * time.Second)
			continue
		}

		newItemsCount := 0

		for _, item := range result.Items {
			if seenItems[item.ID] {
				continue
			}

			img := ""
			if len(item.Photos) > 0 {
				img = item.Photos[0].URI
			}

			// Превращаем цену из строки в число (наш бот ждет int)
			priceInt, _ := strconv.Atoi(item.Price)

			msg := ProductMessage{
				Platform: "mercari",
				ID:       item.ID,
				Name:     item.Name,
				Price:    priceInt,
				URL:      "https://jp.mercari.com/item/" + item.ID,
				PhotoURL: img,
			}

			msgBytes, _ := json.Marshal(msg)

			ch.PublishWithContext(context.Background(), "", q.Name, false, false, amqp.Publishing{
				ContentType: "application/json",
				Body:        msgBytes,
			})

			fmt.Printf("📬 Отправлено в очередь: %s (Цена: %d, Ссылка: %s)\n", msg.Name, msg.Price, msg.URL)

			seenItems[item.ID] = true
			newItemsCount++
		}

		if newItemsCount == 0 {
			fmt.Println("🤷 Новых товаров пока нет.")
		}

		time.Sleep(15 * time.Second)
	}
}
