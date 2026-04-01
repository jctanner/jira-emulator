"""Version, IssueFixVersion, and IssueAffectsVersion models."""

from datetime import date

from sqlalchemy import Boolean, Date, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from jira_emulator.database import Base


class Version(Base):
    __tablename__ = "versions"
    __table_args__ = (UniqueConstraint("project_id", "name"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("projects.id"), nullable=False
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    released: Mapped[bool] = mapped_column(Boolean, default=False)
    release_date: Mapped[date | None] = mapped_column(Date)
    start_date: Mapped[date | None] = mapped_column(Date)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    project: Mapped["Project"] = relationship(back_populates="versions")


class IssueFixVersion(Base):
    __tablename__ = "issue_fix_versions"

    issue_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("issues.id", ondelete="CASCADE"), primary_key=True
    )
    version_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("versions.id"), primary_key=True
    )

    version: Mapped["Version"] = relationship()


class IssueAffectsVersion(Base):
    __tablename__ = "issue_affects_versions"

    issue_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("issues.id", ondelete="CASCADE"), primary_key=True
    )
    version_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("versions.id"), primary_key=True
    )

    version: Mapped["Version"] = relationship()
