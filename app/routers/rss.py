"""Routes for serving RSS feeds."""

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response
from sqlalchemy.orm import Session, joinedload

from ..database import get_db
from ..models import Feed, FeedBook
from ..services.feed_generator import FeedGeneratorService

# No prefix here on purpose: main.py mounts this router at BOTH "/feeds" (the
# original path, kept so existing subscriptions keep resolving) and "/feed" (the
# path advertised as rss_url in api_v2/feeds.py).
router = APIRouter(tags=["RSS"])


@router.get("/{slug}.xml")
async def get_rss_feed(slug: str, db: Session = Depends(get_db)):
    """
    Serve RSS feed by slug.

    This is the public endpoint that podcast apps will subscribe to.
    """
    # Find feed by slug with eager loading to prevent N+1 queries
    feed = (
        db.query(Feed)
        .options(joinedload(Feed.feed_books).joinedload(FeedBook.book))
        .filter(Feed.slug == slug)
        .first()
    )

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

    # Generate RSS XML
    feed_generator = FeedGeneratorService(db)
    rss_xml = feed_generator.generate_rss(feed)

    # Return XML response
    return Response(
        content=rss_xml,
        media_type="text/xml",
        headers={
            "Content-Type": "text/xml; charset=utf-8",
        },
    )


@router.get("/{slug}.xml/preview")
async def preview_rss_feed(slug: str, db: Session = Depends(get_db)):
    """
    Preview RSS feed (returns raw XML for debugging).

    This endpoint is accessible regardless of public/private status.
    """
    # Find feed by slug with eager loading to prevent N+1 queries
    feed = (
        db.query(Feed)
        .options(joinedload(Feed.feed_books).joinedload(FeedBook.book))
        .filter(Feed.slug == slug)
        .first()
    )

    if not feed:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Feed not found: {slug}",
        )

    # Generate RSS XML
    feed_generator = FeedGeneratorService(db)
    rss_xml = feed_generator.generate_rss(feed)

    # Return XML response
    return Response(
        content=rss_xml,
        media_type="text/xml",
        headers={
            "Content-Type": "text/xml; charset=utf-8",
        },
    )
