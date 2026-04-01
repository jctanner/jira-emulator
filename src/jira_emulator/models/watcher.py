"""Watcher model."""

from sqlalchemy import ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship

from jira_emulator.database import Base


class Watcher(Base):
    __tablename__ = "watchers"

    issue_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("issues.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id"), primary_key=True
    )

    user: Mapped["User"] = relationship()


from jira_emulator.models.user import User  # noqa: E402, F401
