"""Authentication service: password hashing, token generation, credential validation."""

import secrets
from datetime import datetime, timedelta

import bcrypt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from jira_emulator.models.api_token import ApiToken
from jira_emulator.models.user import User


def hash_password(password: str) -> str:
    """Hash a plaintext password with bcrypt."""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    """Verify a plaintext password against a bcrypt hash."""
    return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))


def generate_token() -> str:
    """Generate a cryptographically secure random token."""
    return secrets.token_urlsafe(32)


def hash_token(raw_token: str) -> str:
    """Hash a raw API token with bcrypt for storage."""
    return bcrypt.hashpw(raw_token.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_token_hash(raw_token: str, token_hash: str) -> bool:
    """Verify a raw token against its stored bcrypt hash."""
    return bcrypt.checkpw(raw_token.encode("utf-8"), token_hash.encode("utf-8"))


async def create_api_token(
    db: AsyncSession,
    user: User,
    name: str,
    expiration_days: int | None = None,
) -> tuple[ApiToken, str]:
    """Create a new API token for a user.

    Returns (ApiToken model, raw_token_string). The raw token is only
    available at creation time.
    """
    raw_token = generate_token()

    expires_at = None
    if expiration_days is not None:
        expires_at = datetime.utcnow() + timedelta(days=expiration_days)

    token = ApiToken(
        user_id=user.id,
        name=name,
        token_hash=hash_token(raw_token),
        token_prefix=raw_token[:8],
        expires_at=expires_at,
    )
    db.add(token)
    await db.flush()
    return token, raw_token


async def validate_api_token(db: AsyncSession, raw_token: str) -> User | None:
    """Validate a Bearer token and return its owning User, or None."""
    now = datetime.utcnow()
    result = await db.execute(
        select(ApiToken)
        .options(selectinload(ApiToken.user))
        .where(ApiToken.active == True)  # noqa: E712
    )
    tokens = result.scalars().all()

    for token in tokens:
        if token.expires_at and token.expires_at < now:
            continue
        if verify_token_hash(raw_token, token.token_hash):
            token.last_used_at = now
            await db.flush()
            return token.user

    return None


async def authenticate_basic(
    db: AsyncSession, username_or_email: str, password: str
) -> User | None:
    """Authenticate via username/email + password. Returns User or None."""
    # Try username first, then email
    result = await db.execute(
        select(User).where(
            (User.username == username_or_email) | (User.email == username_or_email)
        )
    )
    user = result.scalar_one_or_none()

    if user is None:
        return None
    if user.password_hash is None:
        return None
    if not verify_password(password, user.password_hash):
        return None

    return user


async def change_password(
    db: AsyncSession,
    user: User,
    new_password: str,
    current_password: str | None = None,
) -> bool:
    """Change a user's password. If current_password given, verify it first."""
    if current_password is not None:
        if user.password_hash is None:
            return False
        if not verify_password(current_password, user.password_hash):
            return False

    user.password_hash = hash_password(new_password)
    await db.flush()
    return True
