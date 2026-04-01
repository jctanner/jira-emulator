"""Comment model."""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from jira_emulator.database import Base


class Comment(Base):
    __tablename__ = "comments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    issue_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("issues.id", ondelete="CASCADE"), nullable=False
    )
    author_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"))
    body: Mapped[str] = mapped_column(Text, nullable=False)
    visibility_type: Mapped[str | None] = mapped_column(String)
    visibility_value: Mapped[str | None] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    issue: Mapped["Issue"] = relationship(back_populates="comments")
    author: Mapped["User | None"] = relationship()


from jira_emulator.models.user import User  # noqa: E402, F401
