"""RemoteLink model — web links / hyperlinks attached to issues."""

from sqlalchemy import ForeignKey, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from jira_emulator.database import Base


class RemoteLink(Base):
    __tablename__ = "remote_links"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    issue_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("issues.id", ondelete="CASCADE"), nullable=False
    )
    url: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str | None] = mapped_column(Text)
    icon_url: Mapped[str | None] = mapped_column(Text)
    icon_title: Mapped[str | None] = mapped_column(Text)

    issue: Mapped["Issue"] = relationship(back_populates="remote_links")


from jira_emulator.models.issue import Issue  # noqa: E402, F401
