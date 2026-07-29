"""IssueProperty model — arbitrary JSON key-value store on issues."""

from sqlalchemy import ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from jira_emulator.database import Base


class IssueProperty(Base):
    __tablename__ = "issue_properties"
    __table_args__ = (UniqueConstraint("issue_id", "key"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    issue_id: Mapped[int] = mapped_column(Integer, ForeignKey("issues.id", ondelete="CASCADE"), nullable=False)
    key: Mapped[str] = mapped_column(String(255), nullable=False)
    value: Mapped[str] = mapped_column(Text, nullable=False)

    issue: Mapped["Issue"] = relationship(back_populates="properties")


from jira_emulator.models.issue import Issue  # noqa: E402, F401
