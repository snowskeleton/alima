"""Episode titles in generated RSS feeds.

The "(Unabridged)" stripping used hand-counted slices that were one character
too long, so every Audible title lost its last letter ("Good Omens" became
"Good Omen"). Subtitles were never included at all.
"""

import pytest

from app.models import Book
from app.services.feed_generator import FeedGeneratorService


def item_title(**fields) -> str:
    return FeedGeneratorService._item_title(Book(**fields))


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("Good Omens (Unabridged)", "Good Omens"),
        ("Good Omens(Unabridged)", "Good Omens"),
        ("Everything Is F*cked: A Book About Hope (Unabridged)",
         "Everything Is F*cked: A Book About Hope"),
        ("Good Omens", "Good Omens"),
        ("Dune (Abridged)", "Dune (Abridged)"),
    ],
)
def test_unabridged_marker_is_removed_without_eating_the_title(raw, expected):
    assert item_title(title=raw) == expected


def test_subtitle_is_appended():
    assert item_title(
        title="What Happened to You?",
        subtitle="Conversations on Trauma, Resilience, and Healing",
    ) == "What Happened to You?: Conversations on Trauma, Resilience, and Healing"


def test_subtitle_already_in_the_title_is_not_repeated():
    assert item_title(
        title="Everything Is F*cked: A Book About Hope",
        subtitle="A Book About Hope",
    ) == "Everything Is F*cked: A Book About Hope"


def test_series_is_appended_after_the_subtitle():
    assert item_title(
        title="Wicked", subtitle="The Life and Times of the Wicked Witch of the West",
        series="The Wicked Years", series_position="1",
    ) == (
        "Wicked: The Life and Times of the Wicked Witch of the West: "
        "The Wicked Years, Book 1"
    )


def test_series_named_by_the_subtitle_is_not_repeated():
    assert item_title(
        title="The Great Hunt", subtitle="Book Two of The Wheel of Time",
        series="The Wheel of Time", series_position="2",
    ) == "The Great Hunt: Book Two of The Wheel of Time"


def test_series_matching_the_title_is_dropped():
    assert item_title(title="Ringworld", series="Ringworld!") == "Ringworld"


def test_series_sharing_a_word_with_the_title_is_kept():
    assert item_title(
        title="Dune Messiah", series="Dune", series_position="2"
    ) == "Dune Messiah: Dune, Book 2"
