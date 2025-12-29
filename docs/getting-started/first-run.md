# First Run

After installing and configuring Alima, follow these steps to get started.

## 1. Start the Server

```bash
source .venv/bin/activate
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

You should see output like:

```
✓ Database initialized
✓ Data directories created
✓ Background scheduler started
INFO:     Uvicorn running on http://0.0.0.0:8000
```

## 2. Create Admin Account

The **first user to register** automatically becomes an admin.

1. Open http://localhost:8000 in your browser
2. Click **Register** (or navigate to `/auth/register`)
3. Enter your email and password
4. Click **Create Account**

!!! success "You're now an admin!"
    The first user gets admin privileges automatically. All subsequent users must be invited by an admin.

## 3. Configure Email (Optional)

If you want to send invitation emails:

1. Navigate to **Admin → Server Settings**
2. Fill in the **Email Configuration** section:
   - SMTP Host (e.g., `smtp.gmail.com`)
   - SMTP Port (usually `587`)
   - SMTP Username
   - SMTP Password
   - From Email
   - From Name
3. Click **Send Test Email** to verify it works
4. Click **Save All Settings**

!!! tip "Gmail Users"
    For Gmail, use an [App Password](https://support.google.com/accounts/answer/185833) instead of your regular password.

## 4. Add Your First Audible Account

1. Navigate to **Admin → Audible Accounts**
2. Click **Add Audible Account**
3. Click **Login with Audible**
4. A browser window will open - log in to Audible
5. Return to Alima when complete

The sync will start automatically and download your library metadata.

## 5. Browse Your Library

1. Navigate to **Library**
2. You should see your audiobooks appearing as they sync
3. Click on any book to see details

## 6. Create an RSS Feed (Optional)

To listen in a podcast app:

1. Navigate to **Library → My Feeds**
2. Click **Create New Feed**
3. Give it a name (e.g., "My Audiobooks")
4. Select which books to include
5. Copy the RSS feed URL
6. Add the URL to your podcast app

## 7. Invite Other Users (Optional)

1. Navigate to **Admin → Users**
2. Click **Send Invite**
3. Enter the user's email address
4. Select their role (User or Admin)
5. Click **Send Invite**

They'll receive an email with a registration link.

## What Happens Next?

Alima will automatically:

- **Sync with Audible** every 6 hours (configurable)
- **Download new books** as they appear in your library
- **Update metadata** for existing books
- **Generate RSS feeds** as books are added

## Troubleshooting

### Can't create account

Make sure you're accessing the registration page directly: http://localhost:8000/auth/register

After the first user is created, this page will no longer be accessible (invite-only).

### Audible login fails

Try the external browser login flow:

1. Go to **Admin → Audible Accounts**
2. Click **Add Audible Account**
3. Click **Login with Audible**
4. Complete login in the browser window

### Books aren't syncing

Check the Audible account status:

1. Go to **Admin → Audible Accounts**
2. Look for error messages
3. Try clicking **Sync Now** manually

## Next Steps

- [Managing your library](../user-guide/library.md)
- [Creating RSS feeds](../user-guide/rss-feeds.md)
- [User management](../user-guide/users.md)
