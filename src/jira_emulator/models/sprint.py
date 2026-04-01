"""Sprint and IssueSprint models."""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from jira_emulator.database import Base


class Sprint(Base):
    __tablename__ = "sprints"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    state: Mapped[str] = mapped_column(String, default="future")
    start_date: Mapped[datetime | None] = mapped_column(DateTime)
    end_date: Mapped[datetime | None] = mapped_column(DateTime)
    board_id: Mapped[int | None] = mapped_column(Integer)


class IssueSprint(Base):
    __tablename__ = "issue_sprints"

    issue_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("issues.id", ondelete="CASCADE"), primary_key=True
    )
    sprint_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("sprints.id"), primary_key=True
    )
