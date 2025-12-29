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

Downloads happen in the background with parallel processing (3 concurrent downloads by default). You can continue using Alima while books download.

### Download Quality

Download quality can be configured via **Admin → Server Settings** or in the environment configuration:

- **High** - Best quality (default)
- **Normal** - Good quality, smaller files

### Parallel Downloads

Alima downloads up to 3 books simultaneously by default. This can be adjusted via:

1. Environment variable: `MAX_CONCURRENT_DOWNLOADS=5`
2. **Admin → Server Settings** → "Max Concurrent Downloads"

Higher values mean faster batch downloads but use more bandwidth and system resources.

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

## Importing Existing Audiobooks

If you already have audiobook files downloaded, you can import them without re-downloading:

### Using Book Matching (Recommended)

1. Place your audiobook files (`.m4a`, `.m4b`, `.mp3`) in `data/audiobooks/unassigned/`
2. Navigate to **Admin → Match Books**
3. Review auto-matched files:
   - Files with ≥85% confidence are shown as "Auto-Matched"
   - Click **Confirm Match** for each, or use **Confirm All Auto-Matched**
   - Optionally check "Update metadata" to update book info from the file
4. For unmatched files:
   - **Manual Match**: Select the correct book from the dropdown
   - **Import as New**: Create a new book entry from the file

### Confidence Threshold

The matching algorithm uses fuzzy matching on:

- **Title** (70% weight)
- **Author** (15% weight)
- **Duration** (15% weight)

You can adjust the confidence threshold (50%-100%) using the slider to see more or fewer auto-matches.

### What Gets Updated

When matching files to existing books:

- **Always updated**: File path, file size, format, download date
- **Optional**: Metadata (title, author, narrator, description, etc.)
  - Default: Keep existing Audible metadata
  - Check "Update metadata" to replace with file metadata

### File Requirements

- Supported formats: `.m4a`, `.m4b`, `.mp3`
- Files should have embedded metadata for best matching results
- Cover art is automatically extracted if the book doesn't have one

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
