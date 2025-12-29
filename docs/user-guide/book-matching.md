# Book Matching

Import existing audiobook files by automatically matching them to your Audible library entries.

## Overview

If you already have audiobook files downloaded outside of Alima, you can import them without re-downloading. The book matching feature uses intelligent fuzzy matching to automatically pair files with library entries.

## Quick Start

1. Place audiobook files in `data/audiobooks/unassigned/`
2. Navigate to **Admin → Match Books**
3. Review and confirm matches
4. Done! Files are moved to the main library

## Supported Formats

- `.m4a` - M4A audio files
- `.m4b` - M4B audiobook files (preferred)
- `.mp3` - MP3 audio files

## How Matching Works

The matching algorithm uses fuzzy string matching on multiple metadata fields:

### Matching Criteria

- **Title** (70% weight) - Primary matching field
- **Author** (15% weight) - Secondary verification
- **Duration** (15% weight) - Confirms correct edition/version

### Confidence Threshold

Files are categorized based on their match confidence score:

- **≥85% (default threshold)** - Auto-matched, shown in "Auto-Matched Files" section
- **<85%** - Requires manual review, shown in "Manual Matching Required" section

You can adjust the threshold (50%-100%) using the slider to be more or less strict.

## Using the Match Books Page

### Auto-Matched Files

Files with high confidence matches (≥threshold) are shown here:

1. **Review the match** - Check that the filename matches the book title
2. **Choose metadata handling**:
   - Leave "Update metadata" unchecked (default) to keep Audible metadata
   - Check "Update metadata" to replace book info with file's embedded metadata
3. **Confirm the match** - Click "Confirm Match"

**Batch operation**: Use "Confirm All Auto-Matched" to quickly confirm all high-confidence matches at once.

### Manual Matching Required

Files with low confidence or no matches are shown here:

**Option 1: Manual Match**

1. Select the correct book from the dropdown
2. Choose whether to update metadata
3. Click "Match to Selected"

**Option 2: Import as New**

1. Click "Import as New Book"
2. A new library entry is created from the file's metadata
3. Useful for audiobooks not in your Audible library

## Metadata Handling

When confirming a match, you can choose what happens to the book's metadata:

### Keep Existing Metadata (Default)

- **Recommended for Audible books**
- File path and download info are updated
- Book title, author, description, etc. remain unchanged
- Cover art is extracted if the book doesn't have one

### Update from File Metadata

- Check "Update metadata" option
- All book information is replaced with data from the file:
  - Title
  - Author
  - Narrator
  - Description
  - Publisher
  - Duration
  - Series information
- Useful for files with better/corrected metadata

## What Happens During Matching

1. **File is moved**: From `audiobooks/unassigned/` to `audiobooks/`
2. **Book record is updated**:
   - `file_path` - Set to new location
   - `file_size` - Updated from actual file
   - `file_format` - Set based on extension
   - `downloaded_at` - Set to current timestamp
3. **Cover art is extracted**: If book doesn't have a cover image
4. **Metadata is updated**: If "Update metadata" was checked

## File Organization

After matching:

```
data/audiobooks/
  ├── 20231228_120000_BookTitle.m4b
  ├── 20231228_120001_AnotherBook.m4a
  └── ...
```

Files are renamed with:
- Timestamp (to prevent conflicts)
- Sanitized book title
- Original file extension

## Tips for Best Results

### Ensure Files Have Metadata

For best matching results, files should have embedded metadata tags:

- Title
- Author
- Duration

Most audiobook files include this information by default.

### Pre-Sync Your Audible Library

Run an Audible library sync before matching so all your books are in the database.

### Use Descriptive Filenames

Even without embedded metadata, descriptive filenames help:

- Good: `The_Name_of_the_Wind_Patrick_Rothfuss.m4b`
- Poor: `audiobook_01.m4b`

### Adjust Threshold as Needed

- **High threshold (90-95%)**: More manual matches, but very accurate
- **Medium threshold (80-90%)**: Balanced approach (recommended)
- **Low threshold (50-80%)**: More auto-matches, review carefully

## Troubleshooting

### No Files Shown

**Problem**: The page shows "No files found"

**Solutions**:
- Verify files are in `data/audiobooks/unassigned/` directory
- Check file extensions (must be `.m4a`, `.m4b`, or `.mp3`)
- Refresh the page

### No Auto-Matches

**Problem**: All files show in "Manual Matching Required"

**Solutions**:
- Lower the confidence threshold using the slider
- Verify your Audible library is synced (files match against library entries)
- Check that file metadata is present and accurate

### Wrong Book Matched

**Problem**: A file was matched to the wrong book

**Solutions**:
- Don't confirm it - select the correct book from the dropdown instead
- If already confirmed, delete the file from the book detail page and re-match

### Metadata Not Updating

**Problem**: File metadata not being applied to book

**Solutions**:
- Ensure "Update metadata" checkbox is checked when confirming
- Verify the file actually has embedded metadata tags
- Try using a metadata editor to view/edit file tags

### File Already Exists Error

**Problem**: "File already exists" when matching

**Solutions**:
- This book may already have a file
- Check the book detail page to see if a file is already assigned
- Delete the existing file first if you want to replace it

## Security Considerations

- Only admin users can access the book matching page
- Files must be placed in the designated `unassigned/` directory
- File paths are validated to prevent directory traversal attacks
- File extensions are checked before processing

## Next Steps

After matching your existing files:

- [Manage your library](library.md)
- [Create RSS feeds](rss-feeds.md)
- [Download more books](library.md#downloading-books)
