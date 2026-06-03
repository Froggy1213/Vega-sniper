import enum


class Platform(str, enum.Enum):
    MERCARI = "mercari"


class SubscriptionProvider(str, enum.Enum):
    TELEGRAM_STARS = "telegram_stars"
    STRIPE = "stripe"


class SubscriptionStatus(str, enum.Enum):
    PENDING = "pending"
    ACTIVE = "active"
    CANCELLED = "cancelled"
    EXPIRED = "expired"
