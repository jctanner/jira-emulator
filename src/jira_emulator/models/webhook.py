"""Webhook registrations and durable outbound deliveries."""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from jira_emulator.database import Base


class Webhook(Base):
    __tablename__ = "webhooks"
    __table_args__ = (Index("ix_webhooks_kind_owner", "kind", "owner_user_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    kind: Mapped[str] = mapped_column(String(16), nullable=False, default="admin")
    owner_user_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    project_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("projects.id", ondelete="SET NULL"))
    name: Mapped[str | None] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    events: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    jql_filter: Mapped[str | None] = mapped_column(Text)
    field_ids_filter: Mapped[str | None] = mapped_column(Text)
    issue_property_keys_filter: Mapped[str | None] = mapped_column(Text)
    exclude_body: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    verify_ssl: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    secret: Mapped[str | None] = mapped_column(Text)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime)


class WebhookOutbox(Base):
    __tablename__ = "webhook_outbox"
    __table_args__ = (
        Index("ix_webhook_outbox_due", "state", "next_attempt_at"),
        Index("ix_webhook_outbox_webhook", "webhook_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    webhook_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("webhooks.id", ondelete="SET NULL"))
    owner_user_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id", ondelete="SET NULL"))
    url: Mapped[str] = mapped_column(Text, nullable=False)
    event: Mapped[str] = mapped_column(String(120), nullable=False)
    payload: Mapped[str] = mapped_column(Text, nullable=False, default="")
    secret: Mapped[str | None] = mapped_column(Text)
    verify_ssl: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    flow: Mapped[str] = mapped_column(String(16), nullable=False, default="Primary")
    state: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    last_status: Mapped[int | None] = mapped_column(Integer)
    last_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime)
    failed_at: Mapped[datetime | None] = mapped_column(DateTime)
