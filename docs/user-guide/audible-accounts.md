# Managing Audible Accounts

Learn how to add and manage your Audible accounts in Alima.

## Adding an Audible Account

1. Navigate to **Admin → Audible Accounts**
2. Click **Add Audible Account**
3. Click **Login with Audible**
4. A browser window will open
5. Log in to your Audible account
6. Complete any 2FA challenges if required
7. Close the browser window when complete
8. Return to Alima

Alima will automatically start syncing your library.

## Multiple Accounts

Alima supports multiple Audible accounts per user. This is useful if you have:

- Multiple regional accounts (US, UK, etc.)
- Family accounts
- Separate personal and work accounts

To add additional accounts, repeat the process above.

## Account Status

The Accounts page shows the status of each account:

- **Active** - Account is connected and syncing
- **Syncing** - Currently downloading library metadata
- **Error** - Authentication or sync failed

## Manual Sync

To manually trigger a sync:

1. Go to **Admin → Audible Accounts**
2. Find the account you want to sync
3. Click **Sync Now**

!!! info "Automatic Syncing"
    Alima automatically syncs all accounts every 6 hours (configurable in settings).

## Removing an Account

To remove an Audible account:

1. Go to **Admin → Audible Accounts**
2. Find the account to remove
3. Click **Remove**
4. Confirm the deletion

!!! warning "Audiobooks Not Deleted"
    Removing an account does NOT delete downloaded audiobooks. They remain in your library.

## Troubleshooting

### Login Fails

If the external browser login fails:

- Make sure you're using a supported browser (Chrome, Firefox, Safari)
- Check that you're not blocking cookies
- Try disabling browser extensions temporarily
- Clear your browser cache and try again

### Sync Errors

If syncing fails:

- Check your internet connection
- Verify your Audible account is active
- Try removing and re-adding the account
- Check the application logs for detailed error messages

### Missing Books

If some books don't appear:

- Wait for the sync to complete (can take several minutes for large libraries)
- Check that the books are in your Audible library at audible.com
- Try a manual sync
- Some books may not be available for download (e.g., Audible Plus catalog books)

## What Gets Synced?

When Alima syncs with Audible, it downloads:

- **Metadata** - Title, author, narrator, description
- **Cover art** - Book cover images
- **Purchase info** - Purchase date, ASIN
- **Runtime** - Book length

Audiobook files are NOT downloaded during sync. You must manually download books you want to listen to.

## Privacy & Security

- Audible credentials are encrypted using Snowcrypt
- Authentication files are stored in `AUDIBLE_AUTH_PATH`
- Credentials are never sent to any server except Audible
- Each account has its own encrypted auth file
