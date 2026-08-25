"""API v2 routes for user management."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session

from ...auth import create_magic_link, create_user
from ...database import get_db
from ...dependencies import require_admin
from ...models import Feed, FeedType, User, UserRole
from ...schemas import DatabaseId
from ...services.email_service import EmailService
from ...services.settings_service import SettingsService
from ...utils.tokens import generate_invite_token

router = APIRouter(prefix="/users", tags=["Users"])


def _user_to_dict(user: User) -> dict:
    return {
        "id": user.id,
        "email": user.email,
        "role": user.role.value,
        "receive_notifications": user.receive_notifications,
        "created_at": user.created_at.isoformat() if user.created_at else None,
        "last_login": user.last_login.isoformat() if user.last_login else None,
    }


def _parse_role(value: object) -> UserRole:
    """Coerce a client-supplied role, answering 422 rather than 500 on garbage.

    UserRole() raises ValueError for an unknown value, and both the create and
    patch handlers took the role straight from the request body.
    """
    try:
        return UserRole(value)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Invalid role {value!r}. "
                f"Expected one of: {', '.join(r.value for r in UserRole)}"
            ),
        )


class CreateUserRequest(BaseModel):
    email: EmailStr
    role: str = "user"


@router.get("")
async def list_users(
    sort: str = "created_desc",
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """List all users."""
    sort_field, sort_dir = sort.rsplit("_", 1) if "_" in sort else ("created", "desc")

    users_query = db.query(User)
    if sort_field == "email":
        users_query = users_query.order_by(User.email.asc() if sort_dir == "asc" else User.email.desc())
    elif sort_field == "role":
        users_query = users_query.order_by(User.role.asc() if sort_dir == "asc" else User.role.desc())
    elif sort_field == "last_login":
        users_query = users_query.order_by(User.last_login.asc() if sort_dir == "asc" else User.last_login.desc())
    else:
        users_query = users_query.order_by(User.created_at.asc() if sort_dir == "asc" else User.created_at.desc())

    users = users_query.all()
    return {"users": [_user_to_dict(u) for u in users]}


@router.post("")
async def create_user_endpoint(
    body: CreateUserRequest,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Create a new user and send magic link."""
    existing = db.query(User).filter(User.email == body.email).first()
    if existing:
        raise HTTPException(status_code=400, detail=f"User '{body.email}' already exists")

    user = create_user(db, body.email, role=_parse_role(body.role).value)

    default_feed = Feed(
        user_id=user.id,
        name="My Library",
        description="My personal audiobook collection",
        feed_type=FeedType.SMART,
        filter_criteria=None,
        is_public=False,
        slug=f"my-library-{generate_invite_token(length=8)}",
    )
    db.add(default_feed)
    db.commit()

    token = create_magic_link(db, body.email)
    email_service = EmailService()
    email_sent = await email_service.send_magic_link_email(
        recipient_email=body.email,
        magic_link_token=token,
    )

    magic_url = None
    if not email_sent:
        domain = SettingsService.get_domain(db)
        magic_url = f"{domain}/auth/magic-link?token={token}"

    return {
        "user": _user_to_dict(user),
        "email_sent": email_sent,
        "magic_url": magic_url,
    }


@router.patch("/{user_id}")
async def patch_user(
    user_id: DatabaseId,
    body: dict,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Change role or notifications."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if "role" in body:
        if user.id == current_user.id:
            raise HTTPException(status_code=400, detail="Cannot change your own role")
        user.role = _parse_role(body["role"])

    if "receive_notifications" in body:
        if user.role != UserRole.ADMIN:
            raise HTTPException(status_code=400, detail="Only admins can receive notifications")
        user.receive_notifications = body["receive_notifications"]

    db.commit()
    return _user_to_dict(user)


@router.delete("/{user_id}")
async def delete_user(
    user_id: DatabaseId,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Delete a user."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user.id == current_user.id:
        raise HTTPException(status_code=400, detail="Cannot delete yourself")

    db.delete(user)
    db.commit()
    return {"success": True}


@router.post("/{user_id}/send-login-link")
async def send_login_link(
    user_id: DatabaseId,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Send a magic link login email to a user."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    token = create_magic_link(db, user.email)
    email_service = EmailService()
    email_sent = await email_service.send_magic_link_email(
        recipient_email=user.email,
        magic_link_token=token,
    )

    magic_url = None
    if not email_sent:
        domain = SettingsService.get_domain(db)
        magic_url = f"{domain}/auth/magic-link?token={token}"

    return {"success": True, "email_sent": email_sent, "magic_url": magic_url}
