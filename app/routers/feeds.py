"""Routes for managing RSS feeds."""

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..dependencies import get_current_active_user, get_optional_user, require_admin
from ..models import Feed, FeedBook, FeedType, User
from ..schemas import FeedResponse
from ..services.image_processor import ImageProcessorService
from ..services.settings_service import SettingsService
from ..utils.tokens import generate_invite_token

router = APIRouter(prefix="/feeds", tags=["Feeds"])
feed_detail_router = APIRouter(prefix="/feed", tags=["Feed Detail"])
templates = Jinja2Templates(directory="app/templates")


@router.get("", response_class=HTMLResponse)
async def list_feeds(
    request: Request,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """List all accessible feeds: public feeds + user's private feeds."""
    from ..utils.flash import get_flashed_messages

    # Get all public feeds OR user's own feeds
    feeds = (
        db.query(Feed)
        .filter(
            (Feed.is_public == True) | (Feed.user_id == current_user.id)
        )
        .order_by(Feed.is_pinned.desc(), Feed.created_at.desc())
        .all()
    )

    # Get domain from settings
    domain = SettingsService.get_domain(db)

    return templates.TemplateResponse(
        request=request,
        name="feeds/index.html",
        context={
            "current_user": current_user,
            "feeds": feeds,
            "domain": domain,
            "messages": get_flashed_messages(request),
        },
    )


@router.get("/create", response_class=HTMLResponse)
async def create_feed_page(
    request: Request,
    current_user: User = Depends(get_current_active_user),
):
    """Display feed creation page."""
    return templates.TemplateResponse(
        request=request,
        name="feeds/create.html",
        context={
            "current_user": current_user,
        },
    )


@router.post("/create")
async def create_feed(
    name: str = Form(...),
    description: str = Form(None),
    feed_type: str = Form(...),
    filter_type: str = Form(None),
    filter_value: str = Form(None),
    is_public: bool = Form(True),
    cover_image: UploadFile = File(None),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Create a new feed."""
    # Generate unique slug
    slug = name.lower().replace(" ", "-")
    slug = "".join(c for c in slug if c.isalnum() or c == "-")
    slug = f"{slug}-{generate_invite_token(length=8)}"

    # Build filter criteria for smart feeds
    filter_criteria = None
    if feed_type == "smart" and filter_type and filter_value:
        filter_criteria = {
            "type": filter_type,
            "value": filter_value,
        }

    # Process cover image if provided
    cover_image_path = None
    if cover_image and cover_image.filename:
        try:
            image_processor = ImageProcessorService()
            cover_image_path = await image_processor.process_feed_cover(cover_image)
        except ValueError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(e),
            )

    # Create feed
    feed = Feed(
        user_id=current_user.id,
        name=name,
        description=description,
        feed_type=FeedType(feed_type),
        filter_criteria=filter_criteria,
        is_public=is_public,
        cover_image_path=cover_image_path,
        slug=slug,
    )

    db.add(feed)
    db.commit()
    db.refresh(feed)

    return RedirectResponse(url="/feeds", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/{feed_id}/edit", response_class=HTMLResponse)
async def edit_feed_page(
    request: Request,
    feed_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Display feed edit page."""
    from ..utils.flash import get_flashed_messages

    feed = db.query(Feed).filter(Feed.id == feed_id).first()

    if not feed:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Feed with ID {feed_id} not found",
        )

    # Check ownership (allow admins to edit system feeds)
    is_admin = current_user.role.value == 'admin'
    if feed.user_id != current_user.id and not (is_admin and feed.is_system):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have permission to edit this feed",
        )

    # For manual feeds, get associated books
    books = []
    if feed.feed_type == FeedType.MANUAL:
        books = [fb.book for fb in sorted(feed.feed_books, key=lambda fb: fb.position)]

    return templates.TemplateResponse(
        request=request,
        name="feeds/edit.html",
        context={
            "current_user": current_user,
            "feed": feed,
            "books": books,
            "messages": get_flashed_messages(request),
        },
    )


@router.post("/{feed_id}/update")
async def update_feed(
    feed_id: int,
    name: str = Form(...),
    description: str = Form(None),
    is_public: bool = Form(True),
    filter_type: str = Form(None),
    filter_value: str = Form(None),
    cover_image: UploadFile = File(None),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Update a feed."""
    feed = db.query(Feed).filter(Feed.id == feed_id).first()

    if not feed:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Feed with ID {feed_id} not found",
        )

    # Check ownership (allow admins to edit system feeds)
    is_admin = current_user.role.value == 'admin'
    if feed.user_id != current_user.id and not (is_admin and feed.is_system):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have permission to edit this feed",
        )

    # Process cover image if provided
    if cover_image and cover_image.filename:
        try:
            image_processor = ImageProcessorService()

            # Delete old cover if exists
            if feed.cover_image_path:
                image_processor.delete_cover(feed.cover_image_path)

            # Process and save new cover
            feed.cover_image_path = await image_processor.process_feed_cover(cover_image)
        except ValueError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(e),
            )

    feed.name = name
    feed.description = description
    feed.is_public = is_public

    # Update filter criteria for smart feeds
    if feed.feed_type == FeedType.SMART:
        if filter_type and filter_value:
            feed.filter_criteria = {
                "type": filter_type,
                "value": filter_value,
            }
        else:
            # Clear filter if no type/value provided
            feed.filter_criteria = None

    db.commit()

    return RedirectResponse(url=f"/feed/{feed.slug}", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/{feed_id}/remove-cover")
async def remove_feed_cover(
    request: Request,
    feed_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Remove cover image from a feed."""
    from ..utils.flash import flash

    feed = db.query(Feed).filter(Feed.id == feed_id).first()

    if not feed:
        flash(request, "Feed not found", "error")
        return RedirectResponse(url="/feeds", status_code=status.HTTP_303_SEE_OTHER)

    # Check ownership (allow admins to edit system feeds)
    is_admin = current_user.role.value == 'admin'
    if feed.user_id != current_user.id and not (is_admin and feed.is_system):
        flash(request, "You don't have permission to edit this feed", "error")
        return RedirectResponse(url="/feeds", status_code=status.HTTP_303_SEE_OTHER)

    # Delete cover file if exists
    if feed.cover_image_path:
        image_processor = ImageProcessorService()
        image_processor.delete_cover(feed.cover_image_path)
        feed.cover_image_path = None
        db.commit()
        flash(request, "Cover removed successfully", "success")

    return RedirectResponse(url=f"/feeds/{feed_id}/edit", status_code=status.HTTP_303_SEE_OTHER)


@router.delete("/{feed_id}")
async def delete_feed(
    feed_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Delete a feed."""
    feed = db.query(Feed).filter(Feed.id == feed_id).first()

    if not feed:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Feed with ID {feed_id} not found",
        )

    # Check ownership
    if feed.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have permission to delete this feed",
        )

    db.delete(feed)
    db.commit()

    return {"message": f"Feed '{feed.name}' deleted successfully"}


@router.post("/{feed_id}/add-book")
async def add_book_to_feed(
    feed_id: int,
    book_id: int = Form(...),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Add a book to a manual feed."""
    feed = db.query(Feed).filter(Feed.id == feed_id).first()

    if not feed:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Feed with ID {feed_id} not found",
        )

    # Check ownership
    if feed.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have permission to edit this feed",
        )

    # Check if feed is manual
    if feed.feed_type != FeedType.MANUAL:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Can only add books to manual feeds",
        )

    # Get next position
    max_position = (
        db.query(FeedBook)
        .filter(FeedBook.feed_id == feed_id)
        .count()
    )

    # Add book to feed
    feed_book = FeedBook(
        feed_id=feed_id,
        book_id=book_id,
        position=max_position,
    )

    db.add(feed_book)
    db.commit()

    return {"message": "Book added to feed"}


@router.delete("/{feed_id}/remove-book/{book_id}")
async def remove_book_from_feed(
    feed_id: int,
    book_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Remove a book from a manual feed."""
    feed = db.query(Feed).filter(Feed.id == feed_id).first()

    if not feed:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Feed with ID {feed_id} not found",
        )

    # Check ownership
    if feed.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have permission to edit this feed",
        )

    # Remove book from feed
    feed_book = (
        db.query(FeedBook)
        .filter(FeedBook.feed_id == feed_id, FeedBook.book_id == book_id)
        .first()
    )

    if feed_book:
        db.delete(feed_book)
        db.commit()

    return {"message": "Book removed from feed"}


@router.post("/{feed_id}/pin")
async def pin_feed(
    feed_id: int,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Pin a feed (admin only)."""
    feed = db.query(Feed).filter(Feed.id == feed_id).first()

    if not feed:
        return {"error": "Feed not found"}

    # Only public feeds can be pinned
    if not feed.is_public:
        return {"error": "Only public feeds can be pinned"}

    feed.is_pinned = True
    db.commit()

    return {"success": True, "message": f"Feed '{feed.name}' pinned successfully"}


@router.post("/{feed_id}/unpin")
async def unpin_feed(
    feed_id: int,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Unpin a feed (admin only)."""
    feed = db.query(Feed).filter(Feed.id == feed_id).first()

    if not feed:
        return {"error": "Feed not found"}

    feed.is_pinned = False
    db.commit()

    return {"success": True, "message": f"Feed '{feed.name}' unpinned successfully"}


@feed_detail_router.get("/{slug}", response_class=HTMLResponse)
async def feed_detail_page(
    request: Request,
    slug: str,
    search: str = None,
    sort: str = "added_at",
    order: str = "desc",
    db: Session = Depends(get_db),
    current_user: User = Depends(get_optional_user),
):
    """
    Display feed detail page with RSS auto-discovery.

    This is a public page that shows feed information and books.
    Includes RSS auto-discovery tags for podcast apps.
    Shows navbar if user is logged in.
    Supports searching and sorting books within the feed.
    """
    # Find feed by slug
    feed = db.query(Feed).filter(Feed.slug == slug).first()

    if not feed:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Feed not found: {slug}",
        )

    # Check if feed is public
    if not feed.is_public:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This feed is private",
        )

    # Get books for this feed
    from ..services.feed_generator import FeedGeneratorService
    from ..services.settings_service import SettingsService
    from ..models import Book

    feed_generator = FeedGeneratorService(db)
    all_books = feed_generator._get_feed_books(feed)

    # Get book IDs from feed books
    book_ids = [book.id for book in all_books]

    # Build query for filtering and sorting
    query = db.query(Book).filter(Book.id.in_(book_ids))

    # Apply search filter
    if search:
        search_term = f"%{search}%"
        query = query.filter(
            (Book.title.ilike(search_term))
            | (Book.author.ilike(search_term))
            | (Book.series.ilike(search_term))
            | (Book.narrator.ilike(search_term))
        )

    # Apply sorting
    sort_column = getattr(Book, sort, Book.added_at)
    if order == "desc":
        query = query.order_by(sort_column.desc())
    else:
        query = query.order_by(sort_column.asc())

    # Execute query
    books = query.all()

    # Get domain from database settings (with fallback to config)
    domain = SettingsService.get_domain(db)

    # Generate RSS URL
    rss_url = f"{domain}/feeds/{slug}.xml"

    # Get cover image URL
    cover_url = None
    if feed.cover_image_path:
        cover_url = f"{domain}/files/{feed.cover_image_path}"
    else:
        # Try to get default from settings
        settings_service = SettingsService(db)
        default_cover_path = settings_service.get("default_feed_cover_url")
        if default_cover_path:
            cover_url = f"{domain}/files/{default_cover_path}"

    return templates.TemplateResponse(
        request=request,
        name="feeds/detail.html",
        context={
            "current_user": current_user,
            "feed": feed,
            "books": books,
            "total_count": len(book_ids),
            "filtered_count": len(books),
            "rss_url": rss_url,
            "cover_url": cover_url,
            "domain": domain,
            "filters": {
                "search": search,
                "sort": sort,
                "order": order,
            },
        },
    )
