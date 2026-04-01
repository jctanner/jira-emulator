"""ApiToken model for Personal Access Tokens and API tokens."""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from jira_emulator.database import Base


class ApiToken(Base):
    __tablename__ = "api_tokens"
    __table_args__ = (UniqueConstraint("user_id", "name"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    token_hash: Mapped[str] = mapped_column(String, nullable=False)
    token_prefix: Mapped[str | None] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime)
    active: Mapped[bool] = mapped_column(Boolean, default=True)

    user: Mapped["User"] = relationship()


from jira_emulator.models.user import User  # noqa: E402, F401
