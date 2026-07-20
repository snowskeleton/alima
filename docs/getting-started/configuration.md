# Configuration

Alima can be configured through environment variables in the `.env` file.

## Required Settings

These settings must be configured before running Alima:

### SECRET_KEY

Random secret key used for session encryption and security.

```bash
# Generate with: openssl rand -hex 32
SECRET_KEY=your-random-secret-key-here
```

!!! warning "Security"
    Never commit your secret key to version control! Keep it secret.

### DOMAIN

The full URL where Alima is accessible. Used for generating invite links and RSS feed URLs.

```bash
# Local development
DOMAIN=http://localhost:8000

# Production
DOMAIN=https://alima.yourdomain.com
```

## Optional Settings

### Database

```bash
# SQLite (default)
DATABASE_URL=sqlite:///data/db/alima.db

# PostgreSQL (for production)
DATABASE_URL=postgresql://user:password@localhost/alima
```

### File Paths

Customize where Alima stores files:

```bash
AUDIOBOOKS_PATH=/path/to/audiobooks
COVERS_PATH=/path/to/covers
AUDIBLE_AUTH_PATH=/path/to/audible_auth
TEMP_PATH=/path/to/temp
```

!!! tip "Docker Volumes"
    These paths are especially useful when running in Docker to map volumes.

### Email (SMTP)

Email settings for sending invitation emails. Can also be configured via the web UI at `/admin/settings`.

```bash
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your-email@gmail.com
SMTP_PASSWORD=your-app-password
SMTP_FROM=noreply@yourdomain.com
```

!!! info "Gmail Users"
    For Gmail, you'll need to create an [App Password](https://support.google.com/accounts/answer/185833).

### Sync Settings

```bash
# How often to sync with Audible (in hours)
SYNC_INTERVAL_HOURS=6

# Download quality: High or Normal
DOWNLOAD_QUALITY=High

# Number of parallel downloads (default: 3)
MAX_CONCURRENT_DOWNLOADS=3
```

!!! tip "Parallel Downloads"
    Increasing `MAX_CONCURRENT_DOWNLOADS` speeds up downloading multiple books but uses more bandwidth and system resources. The recommended range is 1-5.

### Session Settings

```bash
# How long sessions last (in hours)
SESSION_EXPIRE_HOURS=168  # 7 days

# How long invite links are valid (in days)
INVITE_EXPIRE_DAYS=7
```

### Backblaze B2 Storage (Optional)

By default Alima stores audiobooks and cover images on local disk and serves them directly. Enabling B2 offloads delivery to Backblaze's servers — podcast clients are redirected to short-lived signed URLs, so large file transfers bypass your home connection entirely.

**Setup:**

1. Create a **private** bucket at [backblaze.com](https://www.backblaze.com)
2. Create an App Key with Read + Write access to that bucket
3. Copy your endpoint URL from *Buckets → Bucket Details → Endpoint*

```bash
B2_ENABLED=true
B2_BUCKET_NAME=my-audiobooks-bucket
B2_ENDPOINT_URL=https://s3.us-west-004.backblazeb2.com
B2_ACCESS_KEY_ID=your-keyID-here
B2_SECRET_ACCESS_KEY=your-applicationKey-here

# How long signed download URLs remain valid (default: 1 hour)
B2_SIGNED_URL_TTL_SECONDS=3600
```

!!! info "RSS feed URLs are unchanged"
    Your podcast app's feed URL (`/feeds/slug.xml`) and enclosure URLs (`/files/audiobooks/...`) stay the same. The server issues a 302 redirect to a signed B2 URL transparently — podcast clients follow it automatically.

!!! tip "Rollout"
    Leave `B2_ENABLED=false` (the default) to keep serving files locally. Once you enable B2, new downloads are uploaded automatically. Existing books without a B2 key continue to be served from disk, so you can migrate gradually.

**Uploading your existing library**

Enabling B2 only affects new downloads. To upload books you already have:

```bash
# See what would be uploaded
python cli.py backfill-b2 --dry-run

# Upload everything (safe to re-run; skips what's already done)
python cli.py backfill-b2

# Or go slower to limit bandwidth
python cli.py backfill-b2 --limit 20 --concurrent 1
```

Uploads also run automatically in the background every 2 minutes, so a freshly downloaded book reaches B2 on its own — the CLI command just does it all at once instead of waiting.

!!! note "Local files are kept"
    Files stay on disk after upload. B2 saves you upload bandwidth when people listen, not disk space. Keeping the local copy is also what lets serving fall back gracefully if a B2 upload hasn't happened yet.

### Advanced Settings

```bash
# Application name
APP_NAME=Alima

# Environment: development, production, testing
ENVIRONMENT=development
```

## Web-Based Configuration

Many settings (especially email settings) can also be configured through the web UI:

1. Log in as an admin user
2. Navigate to **Admin → Server Settings**
3. Configure SMTP and other settings
4. Click **Save All Settings**

!!! success "No Restart Required"
    Settings changed via the web UI take effect immediately - no need to restart the server!

## Environment File Example

A complete `.env.example` file is provided in the repository. Copy it to `.env` and customize:

```bash
cp .env.example .env
nano .env
```

## Next Steps

- [Complete first run setup](first-run.md)
- [Configure email settings via web UI](../user-guide/server-settings.md)
