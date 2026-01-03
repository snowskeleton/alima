"""Authentication utilities for password hashing and JWT tokens."""

from datetime import datetime, timedelta
from typing import Optional

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, InvalidHashError
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from .config import settings
from .models import User
from .schemas import TokenData

# Password hashing with Argon2id (OWASP-recommended, no password length limit)
ph = PasswordHasher()

# JWT settings
ALGORITHM = "HS256"


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verify a password against an Argon2 hash.

    Args:
        plain_password: Plain text password
        hashed_password: Argon2 hashed password from database

    Returns:
        True if password matches, False otherwise
    """
    try:
        ph.verify(hashed_password, plain_password)
        return True
    except (VerifyMismatchError, InvalidHashError):
        return False


def get_password_hash(password: str) -> str:
    """
    Hash a password using Argon2id.

    Argon2id is the modern, OWASP-recommended password hashing algorithm.
    Unlike bcrypt, it has no password length limit.

    Args:
        password: Plain text password

    Returns:
        Hashed password (Argon2id format)
    """
    return ph.hash(password)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """
    Create a JWT access token.

    Args:
        data: Data to encode in the token
        expires_delta: Optional custom expiration time

    Returns:
        Encoded JWT token
    """
    to_encode = data.copy()

    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        # Get session expiration from settings (with hardcoded default)
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
            pass  # Use hardcoded default if DB not available

        expire = datetime.utcnow() + timedelta(hours=session_expire_hours)

    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.secret_key, algorithm=ALGORITHM)
    return encoded_jwt


def verify_token(token: str) -> Optional[TokenData]:
    """
    Verify and decode a JWT token.

    Args:
        token: JWT token to verify

    Returns:
        TokenData if valid, None otherwise
    """
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        user_id: int = payload.get("user_id")

        if email is None:
            return None

        return TokenData(email=email, user_id=user_id)
    except JWTError:
        return None


def authenticate_user(db: Session, email: str, password: str) -> Optional[User]:
    """
    Authenticate a user by email and password.

    Rehashes password if Argon2 parameters have changed (security best practice).

    Args:
        db: Database session
        email: User email
        password: Plain text password

    Returns:
        User object if authentication successful, None otherwise
    """
    user = db.query(User).filter(User.email == email).first()

    if not user:
        return None

    if not verify_password(password, user.password_hash):
        return None

    # Rehash if Argon2 parameters have changed (security best practice)
    try:
        if ph.check_needs_rehash(user.password_hash):
            user.password_hash = get_password_hash(password)
            db.commit()
            db.refresh(user)
    except Exception:
        pass  # If check fails, just continue

    return user


def create_user(db: Session, email: str, password: str, role: str = "user") -> User:
    """
    Create a new user.

    Args:
        db: Database session
        email: User email
        password: Plain text password
        role: User role (admin or user)

    Returns:
        Created User object
    """
    from .models import UserRole

    hashed_password = get_password_hash(password)
    user = User(email=email, password_hash=hashed_password, role=UserRole(role))
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def update_last_login(db: Session, user: User) -> None:
    """
    Update user's last login timestamp.

    Args:
        db: Database session
        user: User object
    """
    user.last_login = datetime.utcnow()
    db.commit()
