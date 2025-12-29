# Database Models

Auto-generated documentation for Alima's database models.

## Overview

Alima uses SQLAlchemy 2.0 with typed mappings for all database models. All models inherit from a declarative `Base` class.

## User

::: app.models.User
    options:
      show_source: false
      heading_level: 3

## Audiobook

::: app.models.Audiobook
    options:
      show_source: false
      heading_level: 3

## AudibleAccount

::: app.models.AudibleAccount
    options:
      show_source: false
      heading_level: 3

## Feed

::: app.models.Feed
    options:
      show_source: false
      heading_level: 3

## FeedBook

::: app.models.FeedBook
    options:
      show_source: false
      heading_level: 3

## Session

::: app.models.Session
    options:
      show_source: false
      heading_level: 3

## Invite

::: app.models.Invite
    options:
      show_source: false
      heading_level: 3

## ServerSettings

::: app.models.ServerSettings
    options:
      show_source: false
      heading_level: 3

## Enums

### UserRole

```python
class UserRole(str, Enum):
    """User role enumeration."""
    ADMIN = "admin"
    USER = "user"
```

### DownloadStatus

```python
class DownloadStatus(str, Enum):
    """Download status enumeration."""
    PENDING = "pending"
    DOWNLOADING = "downloading"
    COMPLETED = "completed"
    FAILED = "failed"
```

## Relationships

The models have the following relationships:

- **User** ↔ **Session**: One-to-many (user can have multiple sessions)
- **User** ↔ **Invite**: One-to-many (user can send multiple invites)
- **User** ↔ **Feed**: One-to-many (user can create multiple feeds)
- **User** ↔ **AudibleAccount**: One-to-many (user can have multiple Audible accounts)
- **AudibleAccount** ↔ **Audiobook**: One-to-many (account has multiple books)
- **Feed** ↔ **FeedBook** ↔ **Audiobook**: Many-to-many through FeedBook
