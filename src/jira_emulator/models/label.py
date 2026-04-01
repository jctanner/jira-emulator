"""Label model."""

from sqlalchemy import ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from jira_emulator.database import Base


class Label(Base):
    __tablename__ = "labels"
    __table_args__ = (UniqueConstraint("issue_id", "label"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    issue_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("issues.id", ondelete="CASCADE"), nullable=False
    )
    label: Mapped[str] = mapped_column(String, nullable=False)

    issue: Mapped["Issue"] = relationship(back_populates="labels")
