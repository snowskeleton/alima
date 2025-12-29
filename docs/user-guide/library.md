# Managing Your Library

Browse, search, and organize your audiobook collection.

## Viewing Your Library

Navigate to **Library** to see all your audiobooks.

The library shows:

- Book cover images
- Title and author
- Narrator
- Runtime
- Download status

## Search

Use the search bar to find books by:

- Title
- Author
- Narrator
- Series name

Search is case-insensitive and matches partial words.

## Filtering

Filter your library by:

- **All Books** - Show everything
- **Downloaded** - Only books with files
- **Not Downloaded** - Books without files
- **By Series** - Group books by series

## Book Details

Click on any book to see:

- Full description
- Metadata (ASIN, purchase date, etc.)
- Chapters (if available)
- Download options

## Downloading Books

To download an audiobook:

1. Click on a book
2. Click **Download**
3. Wait for the download to complete

Downloads happen in the background. You can continue using Alima while books download.

### Download Quality

Download quality is set globally in the environment configuration:

- **Extreme** - Highest quality (default)
- **High** - Good quality, smaller files
- **Normal** - Lower quality, smallest files

### Storage Location

Downloaded audiobooks are stored in:

```
AUDIOBOOKS_PATH/
  ├── Author Name/
  │   └── Book Title/
  │       ├── book.m4b
  │       └── cover.jpg
```

## Progress Tracking

Alima tracks your listening progress for each book:

- Last played position
- Completion percentage
- Last listened date

!!! info "Coming Soon"
    Progress tracking UI is under development.

## Organizing Books

### Series

Books that are part of a series are automatically grouped.

### Tags

!!! info "Coming Soon"
    Custom tagging support is planned for a future release.

## Managing Downloads

### Deleting Books

To free up space:

1. Go to the book details page
2. Click **Delete File**
3. Confirm deletion

This removes the audio file but keeps the metadata in your library.

### Re-downloading

You can re-download any book at any time:

1. Find the book in your library
2. Click on it
3. Click **Download**

## Troubleshooting

### Books Not Appearing

- Wait for the sync to complete
- Check **Admin → Audible Accounts** for sync status
- Try a manual sync

### Download Fails

- Check your internet connection
- Verify you have enough disk space
- Check application logs for errors
- Some books may not be available for download (Audible Plus catalog)

### Missing Metadata

If a book is missing cover art or description:

- Try removing and re-syncing the Audible account
- Check if the metadata exists on audible.com
- Report the issue if it persists
