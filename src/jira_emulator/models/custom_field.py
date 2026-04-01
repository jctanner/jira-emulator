"""CustomField and IssueCustomFieldValue models."""

from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from jira_emulator.database import Base


class CustomField(Base):
    __tablename__ = "custom_fields"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    field_id: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    field_type: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)


class IssueCustomFieldValue(Base):
    __tablename__ = "issue_custom_field_values"
    __table_args__ = (UniqueConstraint("issue_id", "custom_field_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    issue_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("issues.id", ondelete="CASCADE"), nullable=False
    )
    custom_field_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("custom_fields.id"), nullable=False
    )
    value_string: Mapped[str | None] = mapped_column(Text)
    value_number: Mapped[float | None] = mapped_column(Float)
    value_date: Mapped[datetime | None] = mapped_column(DateTime)
    value_json: Mapped[str | None] = mapped_column(Text)

    custom_field: Mapped["CustomField"] = relationship()
