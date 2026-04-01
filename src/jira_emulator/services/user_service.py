"""User service: CRUD operations with password support."""

import re

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from jira_emulator.models.user import User
from jira_emulator.services.auth_service import hash_password


def slugify_username(display_name: str) -> str:
    """Convert a display name to a username slug."""
    slug = display_name.lower().strip()
    slug = re.sub(r"[^a-z0-9]+", ".", slug)
    slug = slug.strip(".")
    return slug or "user"


async def get_user_by_username(db: AsyncSession, username: str) -> User | None:
    result = await db.execute(select(User).where(User.username == username))
    return result.scalar_one_or_none()


async def get_user_by_email(db: AsyncSession, email: str) -> User | None:
    result = await db.execute(select(User).where(User.email == email))
    return result.scalar_one_or_none()


async def get_or_create_user(
    db: AsyncSession,
    display_name: str,
    username: str | None = None,
    password: str | None = None,
) -> User:
    """Look up a user by username, or create one if not found."""
    if username is None:
        username = slugify_username(display_name)

    existing = await get_user_by_username(db, username)
    if existing:
        return existing

    pw_hash = hash_password(password) if password else None
    email = f"{username}@example.com"

    user = User(
        username=username,
        display_name=display_name,
        email=email,
        password_hash=pw_hash,
    )
    db.add(user)
    await db.flush()
    return user


async def create_user(
    db: AsyncSession,
    username: str,
    display_name: str,
    email: str,
    password: str,
) -> User:
    """Create a new user with a hashed password."""
    user = User(
        username=username,
        display_name=display_name,
        email=email,
        password_hash=hash_password(password),
    )
    db.add(user)
    await db.flush()
    return user


async def update_user(
    db: AsyncSession,
    user: User,
    email: str | None = None,
    display_name: str | None = None,
) -> User:
    """Update user email and/or display name."""
    if email is not None:
        user.email = email
    if display_name is not None:
        user.display_name = display_name
    await db.flush()
    return user


async def list_users(db: AsyncSession) -> list[User]:
    result = await db.execute(select(User).where(User.active == True))  # noqa: E712
    return list(result.scalars().all())


async def search_assignable_users(
    db: AsyncSession, project: str | None = None, username: str | None = None
) -> list[User]:
    """Search for users that can be assigned to issues."""
    stmt = select(User).where(User.active == True)  # noqa: E712
    if username:
        stmt = stmt.where(
            (User.username.ilike(f"%{username}%"))
            | (User.display_name.ilike(f"%{username}%"))
        )
    result = await db.execute(stmt.limit(50))
    return list(result.scalars().all())
