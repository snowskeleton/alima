"""Authentication utilities for magic link auth and JWT tokens."""

from datetime import datetime, timedelta
from typing import Optional

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, InvalidHashError
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from .config import settings
from .models import MagicLink, User
from .schemas import TokenData

# Password hashing with Argon2id (kept for backward compat with existing password users)
ph = PasswordHasher()

# JWT settings
ALGORITHM = "HS256"

# Magic link settings
MAGIC_LINK_EXPIRE_MINUTES = 15


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against an Argon2 hash (backward compat)."""
    try:
        ph.verify(hashed_password, plain_password)
        return True
    except (VerifyMismatchError, InvalidHashError):
        return False


def get_password_hash(password: str) -> str:
    """Hash a password using Argon2id (backward compat)."""
    return ph.hash(password)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Create a JWT access token."""
    to_encode = data.copy()

    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        session_expire_hours = 168  # Default: 7 days
        try:
            from .services.settings_service import SettingsService
            from .database import SessionLocal
            db = SessionLocal()
            settings_service = SettingsService(db)
            db_expire = settings_service.get("session_expire_hours")
            if db_expire:
                session_expire_hours = int(db_expire)
            db.close()
        except Exception:
            pass

        expire = datetime.utcnow() + timedelta(hours=session_expire_hours)

    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.secret_key, algorithm=ALGORITHM)
    return encoded_jwt


def verify_token(token: str) -> Optional[TokenData]:
    """Verify and decode a JWT token."""
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        user_id: int = payload.get("user_id")

        if email is None:
            return None

        return TokenData(email=email, user_id=user_id)
    except JWTError:
        return None


def create_user(db: Session, email: str, password: Optional[str] = None, role: str = "user") -> User:
    """Create a new user. Password is optional for magic-link-only users."""
    from .models import UserRole

    hashed_password = get_password_hash(password) if password else None
    user = User(email=email, password_hash=hashed_password, role=UserRole(role))
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def update_last_login(db: Session, user: User) -> None:
    """Update user's last login timestamp."""
    user.last_login = datetime.utcnow()
    db.commit()


def create_magic_link(db: Session, email: str) -> str:
    """Generate a magic link token and store it in the database."""
    from .utils.tokens import generate_magic_link_token

    token = generate_magic_link_token()
    magic_link = MagicLink(
        email=email,
        token=token,
        expires_at=datetime.utcnow() + timedelta(minutes=MAGIC_LINK_EXPIRE_MINUTES),
    )
    db.add(magic_link)
    db.commit()
    return token


def verify_magic_link(db: Session, token: str) -> Optional[User]:
    """Validate a magic link token, mark it used, and return the user."""
    magic_link = (
        db.query(MagicLink)
        .filter(MagicLink.token == token, MagicLink.used == False)
        .first()
    )

    if not magic_link:
        return None

    if magic_link.expires_at < datetime.utcnow():
        return None

    # Mark as used
    magic_link.used = True
    db.commit()

    # Find or return user
    user = db.query(User).filter(User.email == magic_link.email).first()
    return user
