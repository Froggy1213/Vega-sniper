package mercari

import (
	"context"
	"crypto/ecdsa"
	"crypto/elliptic"
	"crypto/rand"
	"encoding/base64"
	"fmt"
	"log/slog"
	mathrand "math/rand"
	"strconv"
	"time"

	"github.com/golang-jwt/jwt/v5"
	"github.com/google/uuid"
	"github.com/imroc/req/v3"

	"mercari/internal/domain"
)

const targetURL = "https://api.mercari.jp/v2/entities:search"

// (Структуры searchPayload, searchCondition, mercariResponse и т.д. оставляем без изменений)
type searchPayload struct {
	PageSize        int             `json:"pageSize"`
	SearchSessionId string          `json:"searchSessionId"`
	SearchCondition searchCondition `json:"searchCondition"`
}

type searchCondition struct {
	Keyword string   `json:"keyword"`
	Sort    string   `json:"sort"`
	Order   string   `json:"order"`
	Status  []string `json:"status"`
}

type mercariResponse struct {
	Items []mercariItem `json:"items"`
}

type mercariItem struct {
	ID     string  `json:"id"`
	Name   string  `json:"name"`
	Price  string  `json:"price"`
	Photos []photo `json:"photos"`
}

type photo struct {
	URI string `json:"uri"`
}

type Client struct {
	proxies []string
	dpotKey *ecdsa.PrivateKey // Переиспользуется между запросами — генерируем один раз
}

// NewClient теперь принимает список прокси-серверов
func NewClient(proxies []string) *Client {
	// Генерируем ECDSA-ключ ОДИН раз при создании клиента
	dpotKey, err := ecdsa.GenerateKey(elliptic.P256(), rand.Reader)
	if err != nil {
		// На практике ошибка здесь почти невозможна, но логируем и паникуем
		slog.Error("Failed to generate ECDSA key for DPoP, exiting", "error", err)
		panic(fmt.Sprintf("ecdsa.GenerateKey: %v", err))
	}
	return &Client{
		proxies: proxies,
		dpotKey: dpotKey,
	}
}

// getReqClient создает HTTP-клиент с имитацией браузера и случайным прокси
func (c *Client) getReqClient() *req.Client {
	client := req.C().ImpersonateChrome().SetTimeout(15 * time.Second)

	if len(c.proxies) > 0 {
		// Выбираем случайный прокси из списка
		randomProxy := c.proxies[mathrand.Intn(len(c.proxies))]
		client.SetProxyURL(randomProxy)
	}

	return client
}

func (c *Client) SearchItems(ctx context.Context, condition domain.SearchCondition) ([]domain.Item, error) {
	dpopToken, err := c.generateDPoP("POST", targetURL)
	if err != nil {
		return nil, err
	}

	payload := searchPayload{
		PageSize:        10,
		SearchSessionId: uuid.New().String(),
		SearchCondition: searchCondition{
			Keyword: condition.Keyword,
			Sort:    "SORT_CREATED_TIME",
			Order:   "ORDER_DESC",
			Status:  []string{"STATUS_ON_SALE"},
		},
	}

	var result mercariResponse

	// Используем динамический клиент (со случайным прокси)
	httpClient := c.getReqClient()

	resp, err := httpClient.R().
		SetContext(ctx).
		SetHeader("X-Platform", "web").
		SetHeader("Accept", "application/json").
		SetHeader("DPoP", dpopToken).
		SetBody(&payload).
		SetSuccessResult(&result).
		Post(targetURL)

	if err != nil {
		return nil, err
	}
	if !resp.IsSuccessState() {
		switch resp.StatusCode {
		case 429:
			return nil, fmt.Errorf("mercari rate limited (HTTP 429)")
		case 403:
			return nil, fmt.Errorf("mercari access denied (HTTP 403) — proxy may be blocked")
		case 502, 503, 504:
			return nil, fmt.Errorf("mercari temporarily unavailable (HTTP %d)", resp.StatusCode)
		default:
			slog.Warn("Unexpected Mercari response", "status", resp.StatusCode, "body_snippet", string(resp.Bytes()[:min(len(resp.Bytes()), 200)]))
			return []domain.Item{}, nil
		}
	}

	var domainItems []domain.Item
	for _, mItem := range result.Items {
		img := ""
		if len(mItem.Photos) > 0 {
			img = mItem.Photos[0].URI
		}
		priceInt, err := strconv.Atoi(mItem.Price)
		if err != nil {
			slog.Warn("Invalid price from Mercari, skipping item", "item_id", mItem.ID, "raw_price", mItem.Price, "error", err)
			continue
		}

		domainItems = append(domainItems, domain.Item{
			Platform: "mercari",
			ID:       mItem.ID,
			Name:     mItem.Name,
			Price:    priceInt,
			URL:      "https://jp.mercari.com/item/" + mItem.ID,
			PhotoURL: img,
		})
	}

	return domainItems, nil
}

func (c *Client) generateDPoP(method, url string) (string, error) {
	// Используем заранее сгенерированный ключ вместо создания нового на каждый запрос
	pubKey := c.dpotKey.PublicKey
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

	return token.SignedString(c.dpotKey)
}
