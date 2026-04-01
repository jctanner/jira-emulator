"""IssueLinkType and IssueLink models."""

from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from jira_emulator.database import Base


class IssueLinkType(Base):
    __tablename__ = "issue_link_types"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    inward_description: Mapped[str | None] = mapped_column(String)
    outward_description: Mapped[str | None] = mapped_column(String)


class IssueLink(Base):
    __tablename__ = "issue_links"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    link_type_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("issue_link_types.id"), nullable=False
    )
    inward_issue_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("issues.id", ondelete="CASCADE"), nullable=False
    )
    outward_issue_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("issues.id", ondelete="CASCADE"), nullable=False
    )

    link_type: Mapped["IssueLinkType"] = relationship()
    inward_issue: Mapped["Issue"] = relationship(
        foreign_keys=[inward_issue_id], overlaps="inward_links"
    )
    outward_issue: Mapped["Issue"] = relationship(
        foreign_keys=[outward_issue_id], overlaps="outward_links"
    )
