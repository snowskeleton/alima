"""Pydantic schemas for request/response validation."""

from datetime import datetime
from typing import Annotated, Any, Optional

from fastapi import Path

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from .models import BookSource, FeedType, MetadataSource, UserRole


# User Schemas
class UserBase(BaseModel):
    """Base user schema."""

    email: EmailStr


class UserCreate(UserBase):
    """Schema for creating a user."""

    password: str = Field(..., min_length=8)
    role: UserRole = UserRole.USER


class UserLogin(BaseModel):
    """Schema for user login."""

    email: EmailStr
    password: str


class UserResponse(UserBase):
    """Schema for user response."""

    id: int
    role: UserRole
    created_at: datetime
    last_login: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


# Invite Schemas
class InviteCreate(BaseModel):
    """Schema for creating an invite."""

    email: EmailStr
    role: UserRole = UserRole.USER


class InviteResponse(BaseModel):
    """Schema for invite response."""

    id: int
    email: EmailStr
    role: UserRole
    token: str
    created_at: datetime
    expires_at: datetime
    used: bool

    model_config = ConfigDict(from_attributes=True)


class InviteAccept(BaseModel):
    """Schema for accepting an invite."""

    token: str
    password: str = Field(..., min_length=8)


# Audible Account Schemas
class AudibleAccountCreate(BaseModel):
    """Schema for creating an Audible account."""

    username: str
    auth_file_path: str
    activation_bytes: str = Field(..., min_length=8, max_length=16)
    marketplace: str = Field(..., max_length=10)


class AudibleAccountResponse(BaseModel):
    """Schema for Audible account response."""

    id: int
    username: str
    marketplace: str
    last_sync_timestamp: Optional[datetime] = None
    enabled: bool
    added_at: datetime

    model_config = ConfigDict(from_attributes=True)


# Book Schemas
class BookBase(BaseModel):
    """Base book schema."""

    title: str
    subtitle: Optional[str] = None
    author: Optional[str] = None
    narrator: Optional[str] = None
    series: Optional[str] = None
    series_position: Optional[str] = None
    description: Optional[str] = None
    publisher: Optional[str] = None
    duration_seconds: Optional[int] = None
    genres: Optional[list[str]] = None


class BookCreate(BookBase):
    """Schema for creating a book."""

    source: BookSource
    file_path: Optional[str] = None
    asin: Optional[str] = None
    audible_account_id: Optional[int] = None


class BookUpdate(BaseModel):
    """Schema for updating book metadata."""

    title: Optional[str] = None
    subtitle: Optional[str] = None
    author: Optional[str] = None
    narrator: Optional[str] = None
    series: Optional[str] = None
    series_position: Optional[str] = None
    description: Optional[str] = None
    publisher: Optional[str] = None
    genres: Optional[list[str]] = None


class BookResponse(BookBase):
    """Schema for book response."""

    id: int
    asin: Optional[str] = None
    source: BookSource
    file_path: Optional[str] = None
    file_size: Optional[int] = None
    file_format: Optional[str] = None
    cover_image_path: Optional[str] = None
    download_enabled: bool = True
    metadata_source: MetadataSource
    added_at: datetime
    downloaded_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


# Feed Schemas
class FeedBase(BaseModel):
    """Base feed schema."""

    name: str
    description: Optional[str] = None
    feed_type: FeedType
    is_public: bool = True


class FeedCreate(FeedBase):
    """Schema for creating a feed."""

    slug: str
    filter_criteria: Optional[dict[str, Any]] = None

    @field_validator("slug")
    @classmethod
    def validate_slug(cls, v: str) -> str:
        """Validate slug format."""
        if not v.replace("-", "").replace("_", "").isalnum():
            raise ValueError("Slug must contain only alphanumeric characters, hyphens, and underscores")
        return v


class FeedUpdate(BaseModel):
    """Schema for updating a feed."""

    name: Optional[str] = None
    description: Optional[str] = None
    is_public: Optional[bool] = None
    filter_criteria: Optional[dict[str, Any]] = None


class FeedResponse(FeedBase):
    """Schema for feed response."""

    id: int
    user_id: int
    slug: str
    filter_criteria: Optional[dict[str, Any]] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# Replication Schemas
class ReplicationConfigResponse(BaseModel):
    """Schema for replication config response."""

    id: int
    instance_id: str
    instance_name: str
    mode: str
    paired_instance_url: Optional[str] = None
    last_sync_from_master: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# Token Schemas
class Token(BaseModel):
    """Schema for JWT token."""

    access_token: str
    token_type: str = "bearer"


class TokenData(BaseModel):
    """Schema for token payload data."""

    email: Optional[str] = None
    user_id: Optional[int] = None


# ---------------------------------------------------------------------------
# Shared path-parameter types
# ---------------------------------------------------------------------------

#: A primary-key path parameter.
#:
#: The upper bound is not cosmetic. A URL like /api/v2/books/99999999999999999999
#: is a valid Python int, so without a bound it reaches the database driver and
#: raises OverflowError ("Python int too large to convert to SQLite INTEGER")
#: rather than simply matching no rows — a 500 on what is plainly a client error.
#: Declaring the range makes FastAPI answer 422, and makes the OpenAPI document
#: state the real constraint so generated clients and schema-driven tests agree
#: with the implementation.
DatabaseId = Annotated[int, Path(ge=1, le=2**63 - 1)]
