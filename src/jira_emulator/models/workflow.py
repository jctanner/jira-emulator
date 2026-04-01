"""Workflow and WorkflowTransition models."""

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from jira_emulator.database import Base


class Workflow(Base):
    __tablename__ = "workflows"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)

    transitions: Mapped[list["WorkflowTransition"]] = relationship(
        back_populates="workflow", cascade="all, delete-orphan"
    )


class WorkflowTransition(Base):
    __tablename__ = "workflow_transitions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workflow_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("workflows.id"), nullable=False
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    from_status_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("statuses.id")
    )
    to_status_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("statuses.id"), nullable=False
    )

    workflow: Mapped["Workflow"] = relationship(back_populates="transitions")
    from_status: Mapped["Status | None"] = relationship(
        foreign_keys=[from_status_id]
    )
    to_status: Mapped["Status"] = relationship(foreign_keys=[to_status_id])


from jira_emulator.models.status import Status  # noqa: E402, F401
