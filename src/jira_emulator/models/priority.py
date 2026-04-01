"""Priority model."""

from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from jira_emulator.database import Base


class Priority(Base):
    __tablename__ = "priorities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    icon_url: Mapped[str | None] = mapped_column(String)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
