"""Component and IssueComponent models."""

from sqlalchemy import ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from jira_emulator.database import Base


class Component(Base):
    __tablename__ = "components"
    __table_args__ = (UniqueConstraint("project_id", "name"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("projects.id"), nullable=False
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    lead: Mapped[str | None] = mapped_column(String)

    project: Mapped["Project"] = relationship(back_populates="components")


class IssueComponent(Base):
    __tablename__ = "issue_components"

    issue_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("issues.id", ondelete="CASCADE"), primary_key=True
    )
    component_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("components.id"), primary_key=True
    )

    component: Mapped["Component"] = relationship()
