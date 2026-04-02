"""IssueHistory model — tracks field-level changes on issues."""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from jira_emulator.database import Base


class IssueHistory(Base):
    __tablename__ = "issue_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    issue_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("issues.id", ondelete="CASCADE"), nullable=False
    )
    author_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"))
    field: Mapped[str] = mapped_column(String, nullable=False)
    field_type: Mapped[str] = mapped_column(String, nullable=False, default="jira")
    from_value: Mapped[str | None] = mapped_column(Text)
    from_id: Mapped[str | None] = mapped_column(String)
    to_value: Mapped[str | None] = mapped_column(Text)
    to_id: Mapped[str | None] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    issue: Mapped["Issue"] = relationship(back_populates="history_entries")
    author: Mapped["User | None"] = relationship()


from jira_emulator.models.issue import Issue  # noqa: E402, F401
from jira_emulator.models.user import User  # noqa: E402, F401
