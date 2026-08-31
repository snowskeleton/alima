"""Contract tests for /api/v2/feeds.

Feeds are the only per-user resource in the app, so most of this file is about
the ownership boundary: which of Alice's feeds Bob can see, read, change, and
delete. That boundary was enforced inconsistently -- list_feeds filtered on it
while get_feed did not -- so it is asserted endpoint by endpoint rather than
once.
"""

from __future__ import annotations

import io
import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.auth import create_access_token
from app.models import Feed, FeedBook, FeedType, User


@pytest.fixture
def alice(test_user: User) -> User:
    """The owner. `test_user` under a name that reads better in these tests."""
    return test_user


@pytest.fixture
def bob(second_user: User) -> User:
    """A second, unrelated user."""
    return second_user


@pytest.fixture
def bob_client(client: TestClient, bob: User) -> TestClient:
    token = create_access_token(data={"sub": bob.email, "user_id": bob.id})
    client.cookies.set("session_token", token)
    client.headers.update({"Accept": "application/json"})
    return client


@pytest.fixture
def alice_private(make_feed, alice: User) -> Feed:
    return make_feed(alice, name="Alice Private", slug="alice-private", is_public=False)


@pytest.fixture
def alice_public(make_feed, alice: User) -> Feed:
    return make_feed(alice, name="Alice Public", slug="alice-public", is_public=True)


class TestListFeeds:
    def test_lists_own_and_public_only(
        self, bob_client: TestClient, make_feed, alice, bob, alice_private, alice_public
    ):
        make_feed(bob, name="Bob Private", slug="bob-private", is_public=False)

        names = {f["name"] for f in bob_client.get("/api/v2/feeds").json()["feeds"]}
        assert names == {"Bob Private", "Alice Public"}
        assert "Alice Private" not in names

    def test_pinned_feeds_sort_first(
        self, authenticated_client: TestClient, make_feed, alice
    ):
        make_feed(alice, name="Ordinary", slug="ordinary", is_pinned=False)
        make_feed(alice, name="Pinned", slug="pinned", is_pinned=True)

        names = [f["name"] for f in authenticated_client.get("/api/v2/feeds").json()["feeds"]]
        assert names[0] == "Pinned"

    def test_rss_url_is_built_from_the_slug(
        self, authenticated_client: TestClient, alice_public
    ):
        feeds = authenticated_client.get("/api/v2/feeds").json()["feeds"]
        entry = next(f for f in feeds if f["slug"] == "alice-public")
        assert entry["rss_url"].endswith("/feed/alice-public.xml")


class TestGetFeedById:
    """Regression coverage for a missing authorization check.

    get_feed looked the feed up by id and returned it -- including its book list
    -- without asking whether the caller was allowed to see it, while every
    sibling endpoint checked ownership and list_feeds filtered on it.
    """

    def test_owner_can_read_their_private_feed(
        self, authenticated_client: TestClient, alice_private
    ):
        response = authenticated_client.get(f"/api/v2/feeds/{alice_private.id}")
        assert response.status_code == 200
        assert response.json()["name"] == "Alice Private"

    def test_other_user_cannot_read_a_private_feed(
        self, bob_client: TestClient, alice_private
    ):
        response = bob_client.get(f"/api/v2/feeds/{alice_private.id}")
        assert response.status_code == 403, (
            "a private feed must not be readable by id just because the caller "
            "is logged in; list_feeds already hides it from them"
        )

    def test_other_user_can_read_a_public_feed(
        self, bob_client: TestClient, alice_public
    ):
        assert bob_client.get(f"/api/v2/feeds/{alice_public.id}").status_code == 200

    def test_admin_can_read_a_system_feed(
        self, admin_client: TestClient, make_feed, test_user
    ):
        system = make_feed(
            test_user, name="System", slug="system", is_public=False, is_system=True
        )
        assert admin_client.get(f"/api/v2/feeds/{system.id}").status_code == 200

    def test_manual_feed_includes_its_books_in_order(
        self, authenticated_client: TestClient, test_db: Session, make_feed, make_book, alice
    ):
        feed = make_feed(alice, feed_type=FeedType.MANUAL, slug="ordered")
        first, second = make_book(title="First"), make_book(title="Second")
        # Inserted out of order to prove the response sorts by position.
        test_db.add(FeedBook(feed_id=feed.id, book_id=second.id, position=1))
        test_db.add(FeedBook(feed_id=feed.id, book_id=first.id, position=0))
        test_db.commit()

        body = authenticated_client.get(f"/api/v2/feeds/{feed.id}").json()
        assert [b["title"] for b in body["books"]] == ["First", "Second"]

    def test_missing_feed_is_404(self, authenticated_client: TestClient):
        assert authenticated_client.get("/api/v2/feeds/999999").status_code == 404


class TestGetFeedBySlug:
    def test_public_feed_resolves_anonymously(self, client: TestClient, alice_public):
        response = client.get("/api/v2/feeds/by-slug/alice-public")
        assert response.status_code == 200
        assert "books" in response.json()

    def test_private_feed_is_forbidden_even_for_its_owner(
        self, authenticated_client: TestClient, alice_private
    ):
        """by-slug is the public surface; privacy is decided by the feed, not
        by who is asking."""
        response = authenticated_client.get("/api/v2/feeds/by-slug/alice-private")
        assert response.status_code == 403

    def test_unknown_slug_is_404(self, client: TestClient):
        assert client.get("/api/v2/feeds/by-slug/nope").status_code == 404


class TestCreateFeed:
    def test_creates_a_manual_feed(self, authenticated_client: TestClient):
        response = authenticated_client.post(
            "/api/v2/feeds", data={"name": "My Feed", "feed_type": "manual"}
        )
        assert response.status_code == 200
        body = response.json()
        assert body["name"] == "My Feed"
        assert body["feed_type"] == "manual"

    def test_slug_is_derived_from_the_name_and_suffixed(
        self, authenticated_client: TestClient
    ):
        body = authenticated_client.post(
            "/api/v2/feeds", data={"name": "My Great Feed", "feed_type": "manual"}
        ).json()
        assert body["slug"].startswith("my-great-feed-"), body["slug"]

    def test_slugs_are_unique_for_identical_names(
        self, authenticated_client: TestClient
    ):
        """Two feeds called the same thing must not collide on one RSS URL."""
        slugs = {
            authenticated_client.post(
                "/api/v2/feeds", data={"name": "Same Name", "feed_type": "manual"}
            ).json()["slug"]
            for _ in range(3)
        }
        assert len(slugs) == 3

    def test_punctuation_is_stripped_from_the_slug(
        self, authenticated_client: TestClient
    ):
        body = authenticated_client.post(
            "/api/v2/feeds", data={"name": "Tom's Picks!", "feed_type": "manual"}
        ).json()
        # startswith rather than splitting off the suffix: the uniqueness token
        # is URL-safe base64 and can itself contain "-", so rsplit("-", 1) picks
        # the wrong boundary roughly one run in ten.
        assert body["slug"].startswith("toms-picks-"), body["slug"]

    def test_smart_feed_stores_its_filters(
        self, authenticated_client: TestClient, test_db: Session
    ):
        filters = [{"field": "author", "op": "eq", "value": "Ann"}]
        body = authenticated_client.post(
            "/api/v2/feeds",
            data={
                "name": "Smart",
                "feed_type": "smart",
                "filters_json": json.dumps(filters),
            },
        ).json()
        assert body["filter_criteria"] == {"filters": filters}

    def test_malformed_filters_json_is_tolerated(
        self, authenticated_client: TestClient
    ):
        """Bad filter JSON must not fail feed creation outright."""
        response = authenticated_client.post(
            "/api/v2/feeds",
            data={"name": "Smart", "feed_type": "smart", "filters_json": "{not json"},
        )
        assert response.status_code == 200
        assert response.json()["filter_criteria"] is None

    def test_filters_are_ignored_for_manual_feeds(
        self, authenticated_client: TestClient
    ):
        body = authenticated_client.post(
            "/api/v2/feeds",
            data={
                "name": "Manual",
                "feed_type": "manual",
                "filters_json": json.dumps([{"field": "author"}]),
            },
        ).json()
        assert body["filter_criteria"] is None

    def test_new_feed_belongs_to_its_creator(
        self, authenticated_client: TestClient, alice: User
    ):
        body = authenticated_client.post(
            "/api/v2/feeds", data={"name": "Mine", "feed_type": "manual"}
        ).json()
        assert body["user_id"] == alice.id


class TestUpdateFeed:
    def test_owner_can_update(
        self, authenticated_client: TestClient, test_db: Session, alice_private
    ):
        response = authenticated_client.put(
            f"/api/v2/feeds/{alice_private.id}",
            data={"name": "Renamed", "is_public": "true"},
        )
        assert response.status_code == 200
        test_db.refresh(alice_private)
        assert alice_private.name == "Renamed"
        assert alice_private.is_public is True

    def test_other_user_cannot_update(self, bob_client: TestClient, alice_private):
        response = bob_client.put(
            f"/api/v2/feeds/{alice_private.id}", data={"name": "Hijacked"}
        )
        assert response.status_code == 403

    def test_admin_cannot_update_someone_elses_ordinary_feed(
        self, admin_client: TestClient, alice_private
    ):
        """Admin override is scoped to system feeds, not to all feeds."""
        response = admin_client.put(
            f"/api/v2/feeds/{alice_private.id}", data={"name": "Admin Edit"}
        )
        assert response.status_code == 403

    def test_smart_filters_can_be_cleared(
        self, authenticated_client: TestClient, test_db: Session, make_feed, alice
    ):
        feed = make_feed(
            alice,
            feed_type=FeedType.SMART,
            slug="smart-clear",
            filter_criteria={"filters": [{"field": "author"}]},
        )
        authenticated_client.put(f"/api/v2/feeds/{feed.id}", data={"name": "Smart"})
        test_db.refresh(feed)
        assert feed.filter_criteria is None

    def test_missing_feed_is_404(self, authenticated_client: TestClient):
        assert (
            authenticated_client.put(
                "/api/v2/feeds/999999", data={"name": "x"}
            ).status_code
            == 404
        )


class TestFeedBooks:
    @pytest.fixture
    def manual_feed(self, make_feed, alice):
        return make_feed(alice, feed_type=FeedType.MANUAL, slug="manual")

    def test_owner_can_add_a_book(
        self, authenticated_client: TestClient, test_db: Session, manual_feed, test_book
    ):
        response = authenticated_client.post(
            f"/api/v2/feeds/{manual_feed.id}/books", json={"book_id": test_book.id}
        )
        assert response.status_code == 200
        assert (
            test_db.query(FeedBook).filter(FeedBook.feed_id == manual_feed.id).count()
            == 1
        )

    def test_positions_increment(
        self, authenticated_client: TestClient, test_db: Session, manual_feed, make_book
    ):
        for _ in range(3):
            authenticated_client.post(
                f"/api/v2/feeds/{manual_feed.id}/books",
                json={"book_id": make_book().id},
            )
        positions = sorted(
            fb.position
            for fb in test_db.query(FeedBook).filter(
                FeedBook.feed_id == manual_feed.id
            )
        )
        assert positions == [0, 1, 2]

    def test_unknown_book_is_404_not_a_crash(
        self, authenticated_client: TestClient, manual_feed
    ):
        """The foreign key raised IntegrityError, surfacing as a 500."""
        response = authenticated_client.post(
            f"/api/v2/feeds/{manual_feed.id}/books", json={"book_id": 999999}
        )
        assert response.status_code == 404

    def test_adding_the_same_book_twice_does_not_duplicate(
        self, authenticated_client: TestClient, test_db: Session, manual_feed, test_book
    ):
        """Position is derived from the row count, so a duplicate collides."""
        for _ in range(2):
            authenticated_client.post(
                f"/api/v2/feeds/{manual_feed.id}/books", json={"book_id": test_book.id}
            )
        assert (
            test_db.query(FeedBook).filter(FeedBook.feed_id == manual_feed.id).count()
            == 1
        )

    def test_missing_book_id_is_400(
        self, authenticated_client: TestClient, manual_feed
    ):
        response = authenticated_client.post(
            f"/api/v2/feeds/{manual_feed.id}/books", json={}
        )
        assert response.status_code == 400

    def test_smart_feeds_reject_manual_additions(
        self, authenticated_client: TestClient, make_feed, alice, test_book
    ):
        smart = make_feed(alice, feed_type=FeedType.SMART, slug="smart-add")
        response = authenticated_client.post(
            f"/api/v2/feeds/{smart.id}/books", json={"book_id": test_book.id}
        )
        assert response.status_code == 400

    def test_other_user_cannot_add(
        self, bob_client: TestClient, manual_feed, test_book
    ):
        response = bob_client.post(
            f"/api/v2/feeds/{manual_feed.id}/books", json={"book_id": test_book.id}
        )
        assert response.status_code == 403

    def test_owner_can_remove_a_book(
        self, authenticated_client: TestClient, test_db: Session, manual_feed, test_book
    ):
        authenticated_client.post(
            f"/api/v2/feeds/{manual_feed.id}/books", json={"book_id": test_book.id}
        )
        response = authenticated_client.delete(
            f"/api/v2/feeds/{manual_feed.id}/books/{test_book.id}"
        )
        assert response.status_code == 200
        assert (
            test_db.query(FeedBook).filter(FeedBook.feed_id == manual_feed.id).count()
            == 0
        )

    def test_removing_a_book_that_is_not_there_is_not_an_error(
        self, authenticated_client: TestClient, manual_feed, test_book
    ):
        response = authenticated_client.delete(
            f"/api/v2/feeds/{manual_feed.id}/books/{test_book.id}"
        )
        assert response.status_code == 200

    def test_other_user_cannot_remove(
        self, bob_client: TestClient, manual_feed, test_book
    ):
        response = bob_client.delete(
            f"/api/v2/feeds/{manual_feed.id}/books/{test_book.id}"
        )
        assert response.status_code == 403


class TestDeleteFeed:
    def test_owner_can_delete(
        self, authenticated_client: TestClient, test_db: Session, alice_private
    ):
        feed_id = alice_private.id
        assert (
            authenticated_client.delete(f"/api/v2/feeds/{feed_id}").status_code == 200
        )
        assert test_db.query(Feed).filter(Feed.id == feed_id).first() is None

    def test_other_user_cannot_delete(self, bob_client: TestClient, alice_private):
        assert bob_client.delete(f"/api/v2/feeds/{alice_private.id}").status_code == 403

    def test_admin_cannot_delete_someone_elses_feed(
        self, admin_client: TestClient, alice_private
    ):
        assert (
            admin_client.delete(f"/api/v2/feeds/{alice_private.id}").status_code == 403
        )

    def test_deleting_a_feed_removes_its_book_links(
        self, authenticated_client: TestClient, test_db: Session, make_feed, alice, test_book
    ):
        feed = make_feed(alice, feed_type=FeedType.MANUAL, slug="cascade")
        authenticated_client.post(
            f"/api/v2/feeds/{feed.id}/books", json={"book_id": test_book.id}
        )
        authenticated_client.delete(f"/api/v2/feeds/{feed.id}")
        assert test_db.query(FeedBook).filter(FeedBook.feed_id == feed.id).count() == 0

    def test_missing_feed_is_404(self, authenticated_client: TestClient):
        assert authenticated_client.delete("/api/v2/feeds/999999").status_code == 404


class TestPinFeed:
    def test_requires_admin(self, authenticated_client: TestClient, alice_private):
        response = authenticated_client.patch(
            f"/api/v2/feeds/{alice_private.id}", json={"is_pinned": True}
        )
        assert response.status_code == 403

    def test_admin_can_pin_and_unpin(
        self, admin_client: TestClient, test_db: Session, alice_private
    ):
        admin_client.patch(
            f"/api/v2/feeds/{alice_private.id}", json={"is_pinned": True}
        )
        test_db.refresh(alice_private)
        assert alice_private.is_pinned is True

        admin_client.patch(
            f"/api/v2/feeds/{alice_private.id}", json={"is_pinned": False}
        )
        test_db.refresh(alice_private)
        assert alice_private.is_pinned is False


class TestFeedCover:
    def test_rejects_a_non_image_upload(
        self, authenticated_client: TestClient, alice_private
    ):
        response = authenticated_client.put(
            f"/api/v2/feeds/{alice_private.id}",
            data={"name": "Feed"},
            files={"cover_image": ("c.jpg", io.BytesIO(b"nope"), "image/jpeg")},
        )
        assert response.status_code == 400

    def test_removing_an_absent_cover_is_not_an_error(
        self, authenticated_client: TestClient, alice_private
    ):
        response = authenticated_client.delete(
            f"/api/v2/feeds/{alice_private.id}/cover"
        )
        assert response.status_code == 200

    def test_other_user_cannot_remove_a_cover(
        self, bob_client: TestClient, alice_private
    ):
        assert (
            bob_client.delete(f"/api/v2/feeds/{alice_private.id}/cover").status_code
            == 403
        )
