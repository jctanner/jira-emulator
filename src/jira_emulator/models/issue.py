"""Issue and IssueSequence models."""

from datetime import datetime, date

from sqlalchemy import Date, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from jira_emulator.database import Base


class Issue(Base):
    __tablename__ = "issues"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    key: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    project_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("projects.id"), nullable=False
    )
    issue_type_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("issue_types.id"), nullable=False
    )
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    status_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("statuses.id"), nullable=False
    )
    priority_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("priorities.id")
    )
    resolution_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("resolutions.id")
    )
    assignee_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"))
    reporter_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"))
    parent_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("issues.id"))
    due_date: Mapped[date | None] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime)

    project: Mapped["Project"] = relationship()
    issue_type: Mapped["IssueType"] = relationship()
    status: Mapped["Status"] = relationship()
    priority: Mapped["Priority | None"] = relationship()
    resolution: Mapped["Resolution | None"] = relationship()
    assignee: Mapped["User | None"] = relationship(foreign_keys=[assignee_id])
    reporter: Mapped["User | None"] = relationship(foreign_keys=[reporter_id])
    parent: Mapped["Issue | None"] = relationship(
        remote_side=[id], foreign_keys=[parent_id]
    )

    labels: Mapped[list["Label"]] = relationship(
        back_populates="issue", cascade="all, delete-orphan"
    )
    comments: Mapped[list["Comment"]] = relationship(
        back_populates="issue", cascade="all, delete-orphan"
    )
    component_associations: Mapped[list["IssueComponent"]] = relationship(
        cascade="all, delete-orphan"
    )
    fix_version_associations: Mapped[list["IssueFixVersion"]] = relationship(
        cascade="all, delete-orphan"
    )
    affects_version_associations: Mapped[list["IssueAffectsVersion"]] = relationship(
        cascade="all, delete-orphan"
    )
    custom_field_values: Mapped[list["IssueCustomFieldValue"]] = relationship(
        cascade="all, delete-orphan"
    )
    watchers: Mapped[list["Watcher"]] = relationship(cascade="all, delete-orphan")
    sprint_associations: Mapped[list["IssueSprint"]] = relationship(
        cascade="all, delete-orphan"
    )
    outward_links: Mapped[list["IssueLink"]] = relationship(
        foreign_keys="IssueLink.outward_issue_id", cascade="all, delete-orphan",
        overlaps="outward_issue"
    )
    inward_links: Mapped[list["IssueLink"]] = relationship(
        foreign_keys="IssueLink.inward_issue_id", cascade="all, delete-orphan",
        overlaps="inward_issue"
    )


class IssueSequence(Base):
    __tablename__ = "issue_sequences"

    project_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("projects.id"), primary_key=True
    )
    next_number: Mapped[int] = mapped_column(Integer, default=1)

    project: Mapped["Project"] = relationship(back_populates="issue_sequences")


# Forward references
from jira_emulator.models.project import Project  # noqa: E402, F401
from jira_emulator.models.issue_type import IssueType  # noqa: E402, F401
from jira_emulator.models.status import Status  # noqa: E402, F401
from jira_emulator.models.priority import Priority  # noqa: E402, F401
from jira_emulator.models.resolution import Resolution  # noqa: E402, F401
from jira_emulator.models.user import User  # noqa: E402, F401
from jira_emulator.models.label import Label  # noqa: E402, F401
from jira_emulator.models.comment import Comment  # noqa: E402, F401
from jira_emulator.models.component import IssueComponent  # noqa: E402, F401
from jira_emulator.models.version import IssueFixVersion, IssueAffectsVersion  # noqa: E402, F401
from jira_emulator.models.custom_field import IssueCustomFieldValue  # noqa: E402, F401
from jira_emulator.models.watcher import Watcher  # noqa: E402, F401
from jira_emulator.models.sprint import IssueSprint  # noqa: E402, F401
from jira_emulator.models.link import IssueLink  # noqa: E402, F401
