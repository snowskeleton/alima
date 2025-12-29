# Server Settings

Configure Alima through the web-based settings page.

## Accessing Settings

1. Log in as an admin user
2. Navigate to **Admin → Server Settings**

!!! warning "Admin Only"
    Only admin users can access server settings.

## Email Configuration

Configure SMTP settings for sending invitation emails.

### Settings

- **SMTP Host** - Your email server hostname (e.g., `smtp.gmail.com`)
- **SMTP Port** - Usually `587` for TLS or `465` for SSL
- **SMTP Username** - Your email address or username
- **SMTP Password** - Your email password or app password
- **From Email** - Email address that appears in the "From" field
- **From Name** - Display name for sent emails

### Testing Email

After configuring email settings:

1. Enter an email address in the test field
2. Click **Send Test Email**
3. Check your inbox for the test message

!!! tip "Gmail Users"
    Gmail requires an [App Password](https://support.google.com/accounts/answer/185833) instead of your regular password. 2FA must be enabled.

### Common Email Providers

=== "Gmail"
    ```
    SMTP Host: smtp.gmail.com
    SMTP Port: 587
    SMTP Username: your-email@gmail.com
    SMTP Password: [App Password]
    ```

=== "Outlook/Office 365"
    ```
    SMTP Host: smtp.office365.com
    SMTP Port: 587
    SMTP Username: your-email@outlook.com
    SMTP Password: [Your password]
    ```

=== "Yahoo"
    ```
    SMTP Host: smtp.mail.yahoo.com
    SMTP Port: 587
    SMTP Username: your-email@yahoo.com
    SMTP Password: [App Password]
    ```

## General Settings

### Application Name

The name displayed throughout the application and in emails.

Default: `Alima`

### Domain URL

The full URL where Alima is accessible. Used for:

- Generating invite links
- RSS feed URLs
- Email links

Examples:
- `http://localhost:8000` (development)
- `https://alima.yourdomain.com` (production)

**Important**: Use `https://` if behind a reverse proxy with SSL.

### Sync Interval

How often (in hours) Alima syncs with Audible to check for new books and downloads.

Default: `6` hours

Changing this setting will take effect on the next server restart.

### Download Quality

Audio quality for downloaded audiobooks:

- **Extreme** - Highest quality (recommended)
- **High** - Good quality, smaller files
- **Normal** - Lower quality, smallest files

Default: `Extreme`

### Session Expiration

How long (in hours) user sessions last before requiring re-login.

Default: `168` hours (7 days)

### Invite Expiration

How many days invitation links remain valid.

Default: `7` days

## Security

### Password Encryption

Sensitive settings (like SMTP password) are automatically encrypted in the database using Fernet (AES-128).

You'll see a **🔒 Encrypted** badge next to encrypted fields.

### Changing Encrypted Values

For password fields:

- Leave blank to keep the existing password
- Enter a new password to change it
- The field shows `••••••••` but this is just for display

## Saving Settings

After making changes:

1. Click **Save All Settings** at the bottom
2. Wait for the success message
3. Changes take effect immediately (no restart required)

## Environment Variables vs Database

Alima can be configured in two ways:

1. **Environment variables** (`.env` file) - Used on startup
2. **Database settings** - Configured via web UI

Database settings take priority over environment variables. This allows you to:

- Override environment settings without editing files
- Change settings without restarting the server
- Encrypt sensitive values automatically

## Troubleshooting

### Settings Not Saving

- Make sure you're logged in as an admin
- Check browser console for JavaScript errors
- Verify database is writable

### Email Not Working

1. Click **Send Test Email**
2. Check the error message
3. Common issues:
   - Wrong SMTP host or port
   - Invalid credentials
   - App password required (Gmail)
   - Firewall blocking SMTP port

### Changes Not Taking Effect

Settings changed via the web UI take effect immediately for new operations. However:

- Existing sync jobs will complete with old settings
- Background tasks restart on next scheduled run
- Active sessions use existing settings

To force a full restart:

```bash
# Stop the server (Ctrl+C)
# Start it again
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```
