"""IssueType model."""

from sqlalchemy import Boolean, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from jira_emulator.database import Base


class IssueType(Base):
    __tablename__ = "issue_types"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    subtask: Mapped[bool] = mapped_column(Boolean, default=False)
    icon_url: Mapped[str | None] = mapped_column(String)
