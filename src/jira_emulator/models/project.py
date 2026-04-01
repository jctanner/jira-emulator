"""Project, ProjectIssueType, and ProjectWorkflow models."""

from datetime import datetime

from sqlalchemy import ForeignKey, Integer, String, Text, DateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship

from jira_emulator.database import Base


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    key: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    lead: Mapped[str | None] = mapped_column(String)
    project_type_key: Mapped[str] = mapped_column(String, default="software")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    issue_type_associations: Mapped[list["ProjectIssueType"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    workflow_associations: Mapped[list["ProjectWorkflow"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    components: Mapped[list["Component"]] = relationship(back_populates="project")
    versions: Mapped[list["Version"]] = relationship(back_populates="project")
    issue_sequences: Mapped[list["IssueSequence"]] = relationship(
        back_populates="project"
    )


class ProjectIssueType(Base):
    __tablename__ = "project_issue_types"

    project_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("projects.id"), primary_key=True
    )
    issue_type_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("issue_types.id"), primary_key=True
    )

    project: Mapped["Project"] = relationship(back_populates="issue_type_associations")
    issue_type: Mapped["IssueType"] = relationship()


class ProjectWorkflow(Base):
    __tablename__ = "project_workflows"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("projects.id"), nullable=False
    )
    issue_type_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("issue_types.id"), nullable=True
    )
    workflow_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("workflows.id"), nullable=False
    )

    project: Mapped["Project"] = relationship(back_populates="workflow_associations")
    workflow: Mapped["Workflow"] = relationship()


# Forward references resolved in models/__init__.py
from jira_emulator.models.issue_type import IssueType  # noqa: E402, F401
from jira_emulator.models.workflow import Workflow  # noqa: E402, F401
from jira_emulator.models.component import Component  # noqa: E402, F401
from jira_emulator.models.version import Version  # noqa: E402, F401
from jira_emulator.models.issue import IssueSequence  # noqa: E402, F401
