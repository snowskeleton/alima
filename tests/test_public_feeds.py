"""Anonymous access to public feeds, at both the old and new URL prefixes."""
import pytest
from app.models import Feed, FeedType, User


@pytest.fixture
def feeds(test_db):
    db_session = test_db
    u = db_session.query(User).first()
    uid = u.id if u else None
    pub = Feed(name="Pub", slug="all", is_public=True, feed_type=FeedType.MANUAL, user_id=uid)
    priv = Feed(name="Priv", slug="secret", is_public=False, feed_type=FeedType.MANUAL, user_id=uid)
    db_session.add_all([pub, priv])
    db_session.commit()
    return pub, priv


def test_public_feed_xml_at_both_prefixes(client, feeds):
    for prefix in ("/feed", "/feeds"):
        r = client.get(f"{prefix}/all.xml")
        assert r.status_code == 200, (prefix, r.status_code)
        assert "xml" in r.headers["content-type"]
        assert r.text.lstrip().startswith("<?xml")


def test_private_feed_still_forbidden(client, feeds):
    for prefix in ("/feed", "/feeds"):
        assert client.get(f"{prefix}/secret.xml").status_code == 403


def test_missing_feed_is_404_not_spa_html(client, feeds):
    r = client.get("/feed/nope.xml")
    assert r.status_code == 404
