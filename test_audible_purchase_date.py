"""Test script to check Audible API purchase_date field."""

import json
import sys
from pathlib import Path

# Add app to path
sys.path.insert(0, str(Path(__file__).parent))

from app.database import SessionLocal
from app.models import AudibleAccount, Book
from app.config import settings
import audible


def test_audible_api():
    """Test what fields the Audible API returns."""
    db = SessionLocal()

    try:
        # Get first enabled account
        account = db.query(AudibleAccount).filter(AudibleAccount.enabled == True).first()

        if not account:
            print("No enabled Audible accounts found")
            return

        print(f"Testing with account: {account.username}")
        print(f"Auth file: {account.auth_file_path}")
        print()

        # Load auth with proper path
        auth_path = settings.audible_auth_path / account.auth_file_path
        print(f"Full auth path: {auth_path}")
        auth = audible.Authenticator.from_file(str(auth_path))

        # Create client
        with audible.Client(auth=auth) as client:
            # Fetch library with all response groups
            params = {
                "response_groups": "contributors, media, product_desc, series, product_extended_attrs, product_attrs",
                "num_results": 5,  # Just get 5 books for testing
                "page": 1,
            }

            print("Fetching library from Audible...")
            library = client.get("1.0/library", params=params)

            if not library or "items" not in library:
                print("Failed to fetch library")
                return

            items = library.get("items", [])
            print(f"Retrieved {len(items)} books")
            print()

            # Check first book for purchase_date
            if items:
                first_book = items[0]
                print("=" * 80)
                print("FIRST BOOK DATA:")
                print("=" * 80)

                # Print all keys
                print("\nAvailable fields:")
                for key in sorted(first_book.keys()):
                    print(f"  - {key}")

                # Check for purchase-related fields
                print("\nPurchase-related fields:")
                purchase_fields = [k for k in first_book.keys() if 'purchase' in k.lower() or 'date' in k.lower()]
                for field in purchase_fields:
                    value = first_book.get(field)
                    print(f"  {field}: {value}")

                # Show full book data (pretty printed)
                print("\nFull book data:")
                print(json.dumps(first_book, indent=2, default=str))

                print("\n" + "=" * 80)

                # Now check database to see if any books have purchased_at set
                print("\nChecking database for purchased_at values...")
                books_with_purchase = db.query(Book).filter(Book.purchased_at.isnot(None)).limit(5).all()

                if books_with_purchase:
                    print(f"Found {len(books_with_purchase)} books with purchased_at set:")
                    for book in books_with_purchase:
                        print(f"  - {book.title}: {book.purchased_at}")
                else:
                    print("No books have purchased_at set in database")

                # Check a specific book
                if first_book.get("asin"):
                    asin = first_book["asin"]
                    db_book = db.query(Book).filter(Book.asin == asin).first()
                    if db_book:
                        print(f"\nDatabase record for {db_book.title}:")
                        print(f"  ASIN: {db_book.asin}")
                        print(f"  Added at: {db_book.added_at}")
                        print(f"  Downloaded at: {db_book.downloaded_at}")
                        print(f"  Purchased at: {db_book.purchased_at}")
                        print(f"  Publish date: {db_book.publish_date}")

    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

    finally:
        db.close()


if __name__ == "__main__":
    test_audible_api()
