"""User service: CRUD operations with password support."""

import re

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from jira_emulator.models.api_token import ApiToken
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


async def create_managed_user(
    db: AsyncSession,
    username: str,
    display_name: str,
    email: str,
    password: str,
) -> User:
    """Create a user after applying admin lifecycle validation."""
    username = username.strip()
    display_name = display_name.strip()
    email = email.strip().lower()
    if not username or not display_name or not email or not password:
        raise ValueError("Username, display name, email, and password are required.")
    if not re.fullmatch(r"[A-Za-z0-9._-]+", username):
        raise ValueError("Username may contain only letters, numbers, dots, underscores, and hyphens.")

    existing = await db.execute(select(User.id).where(func.lower(User.username) == username.lower()))
    if existing.scalar_one_or_none() is not None:
        raise ValueError(f"A user with username '{username}' already exists.")
    await _ensure_email_available(db, email)
    return await create_user(db, username, display_name, email, password)


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


async def update_managed_user(
    db: AsyncSession,
    user: User,
    display_name: str,
    email: str,
) -> User:
    """Update identity fields after applying admin lifecycle validation."""
    display_name = display_name.strip()
    email = email.strip().lower()
    if not display_name or not email:
        raise ValueError("Display name and email are required.")
    await _ensure_email_available(db, email, exclude_user_id=user.id)
    return await update_user(db, user, email=email, display_name=display_name)


async def _ensure_email_available(db: AsyncSession, email: str, exclude_user_id: int | None = None) -> None:
    stmt = select(User.id).where(func.lower(User.email) == email.lower())
    if exclude_user_id is not None:
        stmt = stmt.where(User.id != exclude_user_id)
    if (await db.execute(stmt)).scalar_one_or_none() is not None:
        raise ValueError(f"A user with email '{email}' already exists.")


async def set_user_active(db: AsyncSession, user: User, active: bool) -> User:
    """Activate/deactivate a user, revoking tokens on deactivation."""
    user.active = active
    if not active:
        await db.execute(update(ApiToken).where(ApiToken.user_id == user.id).values(active=False))
    await db.flush()
    return user


async def reset_password(db: AsyncSession, user: User, password: str) -> None:
    """Replace a user's password with a newly hashed value."""
    if not password:
        raise ValueError("Password is required.")
    user.password_hash = hash_password(password)
    await db.flush()


async def revoke_user_token(db: AsyncSession, user: User, token_id: int) -> ApiToken | None:
    """Revoke a token only when it belongs to the selected user."""
    result = await db.execute(select(ApiToken).where(ApiToken.id == token_id, ApiToken.user_id == user.id))
    token = result.scalar_one_or_none()
    if token is None:
        return None
    token.active = False
    await db.flush()
    return token


async def list_users(db: AsyncSession) -> list[User]:
    result = await db.execute(select(User).where(User.active == True))  # noqa: E712
    return list(result.scalars().all())


async def search_assignable_users(
    db: AsyncSession, project: str | None = None, username: str | None = None
) -> list[User]:
    """Search for users that can be assigned to issues."""
    stmt = select(User).where(User.active == True)  # noqa: E712
    if username:
        stmt = stmt.where((User.username.ilike(f"%{username}%")) | (User.display_name.ilike(f"%{username}%")))
    result = await db.execute(stmt.limit(50))
    return list(result.scalars().all())
