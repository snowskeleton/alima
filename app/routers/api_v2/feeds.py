"""API v2 routes for feeds."""

import json

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from ...database import get_db
from ...dependencies import get_current_active_user, get_optional_user, require_admin
from ...models import Book, Feed, FeedBook, FeedType, User
from ...schemas import DatabaseId
from ...services.image_processor import ImageProcessorService
from ...services.settings_service import SettingsService
from ...utils.tokens import generate_invite_token

router = APIRouter(prefix="/feeds", tags=["Feeds"])


def _feed_to_dict(feed: Feed, domain: str = "") -> dict:
    return {
        "id": feed.id,
        "user_id": feed.user_id,
        "name": feed.name,
        "description": feed.description,
        "feed_type": feed.feed_type.value,
        "filter_criteria": feed.filter_criteria,
        "is_public": feed.is_public,
        "is_system": feed.is_system,
        "is_pinned": feed.is_pinned,
        "cover_image_path": feed.cover_image_path,
        "slug": feed.slug,
        "created_at": feed.created_at.isoformat() if feed.created_at else None,
        "updated_at": feed.updated_at.isoformat() if feed.updated_at else None,
        "rss_url": f"{domain}/feed/{feed.slug}.xml" if domain else None,
    }


@router.get("")
async def list_feeds(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """List all accessible feeds."""
    feeds = (
        db.query(Feed)
        .filter((Feed.is_public == True) | (Feed.user_id == current_user.id))
        .order_by(Feed.is_pinned.desc(), Feed.created_at.desc())
        .all()
    )
    domain = SettingsService.get_domain(db)
    return {"feeds": [_feed_to_dict(f, domain) for f in feeds]}


@router.post("")
async def create_feed(
    name: str = Form(...),
    description: str = Form(None),
    feed_type: str = Form(...),
    filters_json: str = Form(None),
    is_public: bool = Form(True),
    cover_image: UploadFile = File(None),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Create a new feed."""
    slug = name.lower().replace(" ", "-")
    slug = "".join(c for c in slug if c.isalnum() or c == "-")
    slug = f"{slug}-{generate_invite_token(length=8)}"

    filter_criteria = None
    if feed_type == "smart" and filters_json:
        try:
            parsed = json.loads(filters_json)
            if isinstance(parsed, list) and len(parsed) > 0:
                filter_criteria = {"filters": parsed}
        except (json.JSONDecodeError, TypeError):
            pass

    cover_image_path = None
    if cover_image and cover_image.filename:
        image_processor = ImageProcessorService()
        try:
            cover_image_path = await image_processor.process_feed_cover(cover_image)
        except ValueError as e:
            # Pillow could not read it, or the format isn't allowed. Both are the
            # uploader's problem, not a server fault.
            raise HTTPException(status_code=400, detail=str(e))

    # FeedType() on an arbitrary form value raises ValueError, which surfaces as
    # a 500. A bad enum value is client error, so answer 422 like the rest of the
    # request-validation layer does.
    try:
        parsed_feed_type = FeedType(feed_type)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Invalid feed_type {feed_type!r}. "
                f"Expected one of: {', '.join(t.value for t in FeedType)}"
            ),
        )

    feed = Feed(
        user_id=current_user.id,
        name=name,
        description=description,
        feed_type=parsed_feed_type,
        filter_criteria=filter_criteria,
        is_public=is_public,
        cover_image_path=cover_image_path,
        slug=slug,
    )
    db.add(feed)
    db.commit()
    db.refresh(feed)

    domain = SettingsService.get_domain(db)
    return _feed_to_dict(feed, domain)


@router.get("/by-slug/{slug}")
async def get_feed_by_slug(
    slug: str,
    current_user: User | None = Depends(get_optional_user),
    db: Session = Depends(get_db),
):
    """Get feed detail by slug (public)."""
    feed = db.query(Feed).filter(Feed.slug == slug).first()
    if not feed:
        raise HTTPException(status_code=404, detail="Feed not found")

    if not feed.is_public:
        raise HTTPException(status_code=403, detail="This feed is private")

    from ...services.feed_generator import FeedGeneratorService

    feed_generator = FeedGeneratorService(db)
    books = feed_generator._get_feed_books(feed)
    domain = SettingsService.get_domain(db)

    from .books import _book_to_dict

    data = _feed_to_dict(feed, domain)
    data["books"] = [_book_to_dict(b) for b in books]
    return data


@router.get("/{feed_id}")
async def get_feed(
    feed_id: DatabaseId,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Get feed detail."""
    feed = db.query(Feed).filter(Feed.id == feed_id).first()
    if not feed:
        raise HTTPException(status_code=404, detail="Feed not found")

    # Readable if it is public, if you own it, or if you are an admin looking at
    # a system feed -- the same rule list_feeds filters on and that every other
    # per-feed endpoint enforces. Without this, a private feed and its book list
    # were readable by any authenticated user who guessed the id, even though
    # list_feeds correctly hid it from them.
    is_admin = current_user.role.value == "admin"
    if (
        not feed.is_public
        and feed.user_id != current_user.id
        and not (is_admin and feed.is_system)
    ):
        raise HTTPException(status_code=403, detail="Permission denied")

    domain = SettingsService.get_domain(db)
    data = _feed_to_dict(feed, domain)

    if feed.feed_type == FeedType.MANUAL:
        books = [fb.book for fb in sorted(feed.feed_books, key=lambda fb: fb.position)]
        from .books import _book_to_dict
        data["books"] = [_book_to_dict(b) for b in books]

    return data


@router.put("/{feed_id}")
async def update_feed(
    feed_id: DatabaseId,
    name: str = Form(...),
    description: str = Form(None),
    is_public: bool = Form(True),
    filters_json: str = Form(None),
    cover_image: UploadFile = File(None),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Update a feed."""
    feed = db.query(Feed).filter(Feed.id == feed_id).first()
    if not feed:
        raise HTTPException(status_code=404, detail="Feed not found")

    is_admin = current_user.role.value == "admin"
    if feed.user_id != current_user.id and not (is_admin and feed.is_system):
        raise HTTPException(status_code=403, detail="Permission denied")

    if cover_image and cover_image.filename:
        image_processor = ImageProcessorService()
        if feed.cover_image_path:
            image_processor.delete_cover(feed.cover_image_path)
        try:
            feed.cover_image_path = await image_processor.process_feed_cover(cover_image)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

    feed.name = name
    feed.description = description
    feed.is_public = is_public

    if feed.feed_type == FeedType.SMART:
        if filters_json:
            try:
                parsed = json.loads(filters_json)
                if isinstance(parsed, list) and len(parsed) > 0:
                    feed.filter_criteria = {"filters": parsed}
                else:
                    feed.filter_criteria = None
            except (json.JSONDecodeError, TypeError):
                feed.filter_criteria = None
        else:
            feed.filter_criteria = None

    db.commit()

    domain = SettingsService.get_domain(db)
    return _feed_to_dict(feed, domain)


@router.delete("/{feed_id}")
async def delete_feed(
    feed_id: DatabaseId,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Delete a feed."""
    feed = db.query(Feed).filter(Feed.id == feed_id).first()
    if not feed:
        raise HTTPException(status_code=404, detail="Feed not found")
    if feed.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Permission denied")

    db.delete(feed)
    db.commit()
    return {"success": True}


@router.post("/{feed_id}/books")
async def add_book_to_feed(
    feed_id: DatabaseId,
    body: dict,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Add a book to a manual feed."""
    feed = db.query(Feed).filter(Feed.id == feed_id).first()
    if not feed:
        raise HTTPException(status_code=404, detail="Feed not found")
    if feed.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Permission denied")
    if feed.feed_type != FeedType.MANUAL:
        raise HTTPException(status_code=400, detail="Only manual feeds accept books")

    book_id = body.get("book_id")
    if not book_id:
        raise HTTPException(status_code=400, detail="book_id required")

    # Check the book exists before inserting. Postgres enforces the foreign key,
    # so an unknown id raised IntegrityError and surfaced as a 500 rather than
    # telling the caller what was wrong.
    if not db.query(Book).filter(Book.id == book_id).first():
        raise HTTPException(status_code=404, detail=f"Book {book_id} not found")

    # Guard against adding the same book twice: the position counter is derived
    # from the row count, so a duplicate would land on a colliding position.
    already_present = (
        db.query(FeedBook)
        .filter(FeedBook.feed_id == feed_id, FeedBook.book_id == book_id)
        .first()
    )
    if already_present:
        return {"success": True, "already_present": True}

    max_pos = db.query(FeedBook).filter(FeedBook.feed_id == feed_id).count()
    fb = FeedBook(feed_id=feed_id, book_id=book_id, position=max_pos)
    db.add(fb)
    db.commit()
    return {"success": True}


@router.delete("/{feed_id}/books/{book_id}")
async def remove_book_from_feed(
    feed_id: DatabaseId,
    book_id: DatabaseId,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Remove a book from a manual feed."""
    feed = db.query(Feed).filter(Feed.id == feed_id).first()
    if not feed:
        raise HTTPException(status_code=404, detail="Feed not found")
    if feed.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Permission denied")

    fb = db.query(FeedBook).filter(
        FeedBook.feed_id == feed_id, FeedBook.book_id == book_id
    ).first()
    if fb:
        db.delete(fb)
        db.commit()
    return {"success": True}


@router.patch("/{feed_id}")
async def patch_feed(
    feed_id: DatabaseId,
    body: dict,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Pin/unpin a feed."""
    feed = db.query(Feed).filter(Feed.id == feed_id).first()
    if not feed:
        raise HTTPException(status_code=404, detail="Feed not found")

    if "is_pinned" in body:
        feed.is_pinned = body["is_pinned"]

    db.commit()
    domain = SettingsService.get_domain(db)
    return _feed_to_dict(feed, domain)


@router.delete("/{feed_id}/cover")
async def remove_cover(
    feed_id: DatabaseId,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Remove cover image from feed."""
    feed = db.query(Feed).filter(Feed.id == feed_id).first()
    if not feed:
        raise HTTPException(status_code=404, detail="Feed not found")

    is_admin = current_user.role.value == "admin"
    if feed.user_id != current_user.id and not (is_admin and feed.is_system):
        raise HTTPException(status_code=403, detail="Permission denied")

    if feed.cover_image_path:
        ImageProcessorService().delete_cover(feed.cover_image_path)
        feed.cover_image_path = None
        db.commit()

    return {"success": True}
