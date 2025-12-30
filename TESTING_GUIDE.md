# Testing Guide: Security & Performance Improvements

## Overview

This guide covers testing for **Phase 1 (Security & Stability)** and **Phase 2 (Code Quality)** improvements made to the Alima 2.0 audiobook library manager.

**Total Changes:**
- ✅ 11 completed improvements
- 📝 1 migration (013_add_indexes_and_cascades)
- 🧪 18 test cases in `tests/test_security_improvements.py`

---

## Prerequisites

### 1. Set a Valid SECRET_KEY

**CRITICAL:** The app will no longer start without a valid SECRET_KEY.

```bash
# Generate a secure key
python -c 'import secrets; print(secrets.token_urlsafe(32))'

# Add to your .env file or environment
echo "SECRET_KEY=<your-generated-key>" >> .env
```

### 2. Install New Dependencies

```bash
# Install slowapi for rate limiting
pip install -r requirements.txt
```

---

## Testing Checklist

### ⚠️ Pre-Deployment Testing (Dev Instance)

#### 1. **SECRET_KEY Validation**

```bash
# Test 1: Start without SECRET_KEY (should FAIL)
unset SECRET_KEY
docker-compose up -d

# Expected: Error message about SECRET_KEY
# "SECRET_KEY must be at least 32 characters long"

# Test 2: Start with valid SECRET_KEY (should SUCCEED)
export SECRET_KEY="your-32-char-key-here"
docker-compose up -d

# Expected: Clean startup
```

#### 2. **Database Migration**

```bash
# Check migration logs
docker-compose logs alima | grep "Migration 013"

# Expected output:
# ✓ Running migration 013_add_indexes_and_cascades...
# ✓ Adding database indexes...
# ✓ Added index on books.file_path
# ✓ Added index on books.audible_account_id
# ✓ Added index on books.source
# ✓ Added index on books.synced_from_master
# ✓ Added index on download_queue.status
# ✓ Updating foreign key constraints with CASCADE behavior...
# ✓ Updated invites.created_by -> CASCADE
# ✓ Updated books.audible_account_id -> SET NULL
# ✓ Updated feeds.user_id -> SET NULL
# ✓ Updated feed_books.feed_id -> CASCADE
# ✓ Updated feed_books.book_id -> CASCADE
# ✓ Updated download_queue.book_id -> CASCADE
# ✓ Updated download_queue.audible_account_id -> CASCADE
# ✓ Migration 013_add_indexes_and_cascades completed successfully!
```

**Verify indexes were created:**

```bash
# Connect to PostgreSQL
docker-compose exec postgres psql -U alima -d alima

# Check indexes
SELECT indexname FROM pg_indexes WHERE tablename = 'books' ORDER BY indexname;

# Expected indexes:
# idx_books_audible_account_id
# idx_books_file_path
# idx_books_source
# idx_books_synced_from_master

SELECT indexname FROM pg_indexes WHERE tablename = 'download_queue' ORDER BY indexname;

# Expected:
# idx_download_queue_status
```

#### 3. **Leader Election & Connection Pool**

```bash
# Verify only 1 leader worker
docker-compose logs alima | grep -E "LEADER|FOLLOWER"

# Expected: 1 LEADER, 3 FOLLOWERS
# Worker XXXX is LEADER - running startup tasks
# Worker YYYY is FOLLOWER - skipping startup tasks
# Worker ZZZZ is FOLLOWER - skipping startup tasks
# Worker WWWW is FOLLOWER - skipping startup tasks

# Check connection pool isn't exhausted
docker-compose exec postgres psql -U alima -d alima -c \
  "SELECT count(*) FROM pg_stat_activity WHERE datname = 'alima';"

# Expected: ~15-60 connections (well under 100)
```

#### 4. **CSRF Protection**

```bash
# Try to POST without CSRF token
curl -X POST http://localhost:8000/auth/login \
  -d "email=test@example.com&password=test" \
  -v

# Expected: 403 Forbidden or 422 Unprocessable Entity
# Should see CSRF error in response
```

#### 5. **Rate Limiting**

```bash
# Hammer login endpoint
for i in {1..15}; do
  curl -X POST http://localhost:8000/auth/login \
    -d "email=test@example.com&password=wrong" \
    -w "%{http_code}\n" -o /dev/null -s
done

# Expected: First 10 succeed (200/303), then 429 Too Many Requests
```

#### 6. **Path Traversal Protection**

```bash
# Try to access file outside allowed directory
curl http://localhost:8000/files/covers/../../../../../../etc/passwd

# Expected: 403 Forbidden or 400 Bad Request

# Same for audiobooks (create a book with ID 1 first)
curl http://localhost:8000/files/audiobooks/../../../etc/passwd

# Expected: 403 Forbidden or 400 Bad Request
```

#### 7. **Foreign Key Cascades**

**Test CASCADE delete:**

```sql
-- Connect to database
docker-compose exec postgres psql -U alima -d alima

-- Create test user
INSERT INTO users (email, password_hash, role)
VALUES ('cascade_test@example.com', 'hash', 'admin');

-- Get user ID
SELECT id FROM users WHERE email = 'cascade_test@example.com';
-- Note the ID (let's say it's 999)

-- Create invite from this user
INSERT INTO invites (email, token, created_by, expires_at, role)
VALUES ('invited@example.com', 'test_token', 999, '2099-01-01', 'user');

-- Delete the user
DELETE FROM users WHERE id = 999;

-- Check if invite was deleted (CASCADE)
SELECT * FROM invites WHERE token = 'test_token';
-- Expected: 0 rows (invite should be deleted)
```

**Test SET NULL:**

```sql
-- Create audible account
INSERT INTO audible_accounts (username, auth_file_path)
VALUES ('test_account', '/path/to/auth');

-- Get account ID
SELECT id FROM audible_accounts WHERE username = 'test_account';
-- Note the ID (let's say it's 888)

-- Create book linked to this account
INSERT INTO books (title, source, audible_account_id)
VALUES ('Test Book', 'AUDIBLE', 888);

-- Delete the audible account
DELETE FROM audible_accounts WHERE id = 888;

-- Check if book's account_id was set to NULL
SELECT audible_account_id FROM books WHERE title = 'Test Book';
-- Expected: NULL (not deleted, just unlinked)
```

#### 8. **Settings Cache**

**Manual test:**

```python
# In Python shell or test
from app.utils.settings_cache import get_cached_setting, clear_settings_cache

# Get a setting (will be cached)
result1 = get_cached_setting("quick_sync_interval_seconds", 60, int)
print(result1)  # Should be 60 (or DB value if set)

# Get again (should be from cache, faster)
result2 = get_cached_setting("quick_sync_interval_seconds", 60, int)
print(result2)  # Same value

# Clear cache
clear_settings_cache()

# Get again (fresh from DB)
result3 = get_cached_setting("quick_sync_interval_seconds", 60, int)
print(result3)  # Same value but from DB
```

**Check logs for cache usage:**

```bash
# Settings should not create new DB connections every time
docker-compose logs alima | grep "SettingsService"

# Before: Many connection/close logs
# After: Minimal connection logs (cached)
```

#### 9. **RSS Feed N+1 Query Fix**

```bash
# Access a feed with many books
curl http://localhost:8000/feeds/all.xml -o /dev/null -w "Time: %{time_total}s\n"

# Note the time, then try again
curl http://localhost:8000/feeds/all.xml -o /dev/null -w "Time: %{time_total}s\n"

# Should be fast (no N+1 queries, eager loading active)
```

---

### 🧪 Automated Testing

Run the test suite:

```bash
# Run all tests
pytest tests/test_security_improvements.py -v

# Run specific test classes
pytest tests/test_security_improvements.py::TestSecretKeyValidation -v
pytest tests/test_security_improvements.py::TestDatabaseIndexes -v
pytest tests/test_security_improvements.py::TestForeignKeyCascades -v

# Run with coverage
pytest tests/test_security_improvements.py --cov=app --cov-report=html
```

**Expected output:**

```
tests/test_security_improvements.py::TestSecretKeyValidation::test_empty_secret_key_raises_error PASSED
tests/test_security_improvements.py::TestSecretKeyValidation::test_short_secret_key_raises_error PASSED
tests/test_security_improvements.py::TestSecretKeyValidation::test_valid_secret_key_accepted PASSED
tests/test_security_improvements.py::TestCSRFProtection::test_csrf_middleware_active PASSED
tests/test_security_improvements.py::TestRateLimiting::test_login_rate_limit PASSED
tests/test_security_improvements.py::TestDatabaseIndexes::test_books_indexes_exist PASSED
tests/test_security_improvements.py::TestDatabaseIndexes::test_download_queue_status_index_exists PASSED
tests/test_security_improvements.py::TestForeignKeyCascades::test_delete_user_cascades_to_invites PASSED
tests/test_security_improvements.py::TestForeignKeyCascades::test_delete_feed_cascades_to_feed_books PASSED
tests/test_security_improvements.py::TestSettingsCache::test_get_cached_setting_returns_default PASSED
tests/test_security_improvements.py::TestSettingsCache::test_get_cached_setting_type_conversion PASSED
tests/test_security_improvements.py::TestSettingsCache::test_clear_settings_cache PASSED
tests/test_security_improvements.py::TestSessionExpiration::test_get_session_expiration_hours_returns_default PASSED
tests/test_security_improvements.py::TestPathTraversalProtection::test_audiobook_serving_validates_path PASSED
tests/test_security_improvements.py::TestPathTraversalProtection::test_cover_serving_validates_path PASSED
tests/test_security_improvements.py::TestN1QueryFix::test_rss_feed_uses_eager_loading PASSED
tests/test_security_improvements.py::TestMigration013::test_migration_is_idempotent PASSED
tests/test_security_improvements.py::TestMigration013::test_migration_creates_indexes PASSED

====================== 18 passed in X.XXs ======================
```

---

## Deployment Steps

### Development Instance

1. **Backup database:**
   ```bash
   docker-compose exec postgres pg_dump -U alima alima > backup_before_migration_013.sql
   ```

2. **Set SECRET_KEY:**
   ```bash
   # Generate and set
   python -c 'import secrets; print(secrets.token_urlsafe(32))' >> .env
   ```

3. **Update code:**
   ```bash
   git pull  # or copy updated files
   ```

4. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   # Or rebuild Docker image
   docker-compose build
   ```

5. **Restart application:**
   ```bash
   docker-compose down
   docker-compose up -d
   ```

6. **Verify migration:**
   ```bash
   docker-compose logs alima | grep "Migration 013"
   ```

7. **Run tests:**
   ```bash
   pytest tests/test_security_improvements.py -v
   ```

### Production Instance

**⚠️ DO NOT deploy directly to production!**

1. Test thoroughly on dev instance first
2. Verify all 9 test scenarios above pass
3. Run automated test suite
4. Monitor for 24-48 hours
5. Only then consider production deployment

**Production deployment checklist:**

- [ ] Dev instance tested for 24+ hours
- [ ] All automated tests pass
- [ ] Database backup created
- [ ] SECRET_KEY generated and stored securely
- [ ] Rollback plan ready
- [ ] Off-hours deployment scheduled
- [ ] Monitoring alerts configured

---

## Rollback Plan

If issues occur:

### Quick Rollback (Code Only)

```bash
# Revert to previous version
git checkout <previous-commit>
docker-compose build
docker-compose up -d
```

### Full Rollback (Including Database)

```bash
# Stop application
docker-compose down

# Restore database
cat backup_before_migration_013.sql | docker-compose exec -T postgres psql -U alima alima

# Remove migration marker
docker-compose exec postgres psql -U alima -d alima -c \
  "DELETE FROM schema_migrations WHERE migration_name = '013_add_indexes_and_cascades';"

# Revert code
git checkout <previous-commit>
docker-compose build
docker-compose up -d
```

**Note:** Foreign key constraints and indexes added by migration will remain (harmless) unless you manually drop them.

---

## Known Issues & Limitations

1. **SQLite:** Foreign key CASCADE updates are skipped (require table recreation)
2. **CSRF:** May require frontend updates to include CSRF tokens in AJAX requests
3. **Rate Limiting:** Currently per-IP; won't prevent distributed attacks
4. **Connection Pool:** Sized for 4 workers; adjust `pool_size` if you change worker count

---

## Performance Baseline

Before deploying, capture baseline metrics:

```bash
# Connection count
docker-compose exec postgres psql -U alima -d alima -c \
  "SELECT count(*) FROM pg_stat_activity WHERE datname = 'alima';"

# Index sizes
docker-compose exec postgres psql -U alima -d alima -c \
  "SELECT tablename, indexname, pg_size_pretty(pg_relation_size(indexrelid))
   FROM pg_stat_user_indexes
   WHERE schemaname = 'public' ORDER BY tablename, indexname;"

# Query performance (feed generation)
time curl http://localhost:8000/feeds/all.xml -o /dev/null
```

Compare these metrics after deployment to verify improvements.

---

## Support

If you encounter issues:

1. Check logs: `docker-compose logs alima | tail -100`
2. Verify SECRET_KEY is set: `docker-compose exec alima env | grep SECRET_KEY`
3. Check migration status: `docker-compose exec postgres psql -U alima -d alima -c "SELECT * FROM schema_migrations ORDER BY applied_at DESC LIMIT 5;"`
4. Review this guide for common issues

For bugs, create an issue with:
- Error logs
- Test results
- Database state (migration status, index list)
