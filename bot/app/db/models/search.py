from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, Boolean, Enum as SQLEnum, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.db.enums import Platform

if TYPE_CHECKING:
    from app.db.models.user import User


class Search(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "searches"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "platform",
            "keyword",
            "price_min",
            "price_max",
            name="uq_searches_user_platform_criteria",
        ),
        Index("ix_searches_platform_active", "platform", "is_active"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    platform: Mapped[Platform] = mapped_column(
        SQLEnum(Platform, native_enum=False, length=32),
        nullable=False,
    )
    keyword: Mapped[str] = mapped_column(String(512), nullable=False)
    price_min: Mapped[int | None] = mapped_column(Integer, nullable=True)
    price_max: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true", nullable=False)

    user: Mapped[User] = relationship(back_populates="searches", lazy="joined")

    def matches_price(self, price: int) -> bool:
        if self.price_min is not None and price < self.price_min:
            return False
        if self.price_max is not None and price > self.price_max:
            return False
        return True

    def __repr__(self) -> str:
        return (
            f"<Search id={self.id} platform={self.platform.value} "
            f"keyword={self.keyword!r} active={self.is_active}>"
        )
