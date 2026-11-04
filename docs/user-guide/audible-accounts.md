# Managing Audible Accounts

Learn how to add and manage your Audible accounts in Alima.

## Adding an Audible Account

Go to **Admin → Audible Accounts** and click **Login with Audible**. There are
two ways to sign in.

### Send a sign-in link (easiest, and works for other people)

1. Pick the marketplace and click **Create sign-in link**.
2. Copy the link and send it to the account's owner (or open it yourself).
3. They click **Get my code**, open `amazon.<tld>/code`, sign in to Amazon and
   type the 5-character code shown.
4. The page notices by itself and the account appears in Alima. Nothing has to
   be sent back.

The link works once and expires after 7 days. Each code it shows lasts about 10
minutes; if one runs out, the page offers a new one. The person signs in on
Amazon's own site, so Alima never sees their password, and they don't need an
Alima login. Alima has to be reachable from their network for the link to work.

Sign-in links don't work for pre-Amazon (username) Audible accounts.

### Sign in here (paste the redirect URL)

1. Pick the marketplace and click **Generate Login URL**.
2. Open the URL, sign in to Amazon, and complete any 2FA challenge.
3. You land on a "page not found" page. Copy its full URL from the address bar.
4. Paste it into Alima and click **Complete Login**.

The pending login is kept for 7 days, so you can also send the URL to the
account's owner and paste in the URL they send back.

## Re-authenticating an Account

Since October 2026, Audible refuses download licenses (`CustomerThrottled`) to
devices registered with an older device profile. Accounts that need it show a
**Needs re-auth** badge. Re-authenticating registers a new device for the same
account; its books and history are kept.

1. Click **Re-authenticate** on the account.
2. Create a sign-in link, or sign in here, as above. Use the **same** Amazon
   account the Audible account was added with; a different one is refused.
3. Once downloads work with the new device, click **Remove old device** to
   deregister the old one from Amazon. This is a separate step on purpose.

There is no way to re-register without a fresh sign-in: Amazon only accepts
recently signed-in credentials for a new device.

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
