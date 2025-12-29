# RSS Feeds

Create RSS feeds to listen to your audiobooks in podcast apps.

## What are RSS Feeds?

RSS feeds allow you to access your audiobooks in any podcast app (Apple Podcasts, Overcast, Pocket Casts, etc.).

Benefits:

- Listen on any device with a podcast app
- Automatic progress syncing (app-dependent)
- Download management by the podcast app
- No need to transfer files manually

## Creating a Feed

1. Navigate to **Library → My Feeds**
2. Click **Create New Feed**
3. Enter a feed name (e.g., "My Audiobooks")
4. Select books to include
5. Click **Create Feed**

You'll receive a unique RSS URL.

## Using the Feed

### In a Podcast App

1. Copy the RSS feed URL
2. Open your podcast app
3. Find "Add by URL" or "Add custom feed"
4. Paste the RSS URL
5. Subscribe

The feed will appear like a podcast with each book as an episode.

### Supported Apps

Most podcast apps support custom RSS feeds:

- **Apple Podcasts** (iOS/Mac)
- **Overcast** (iOS)
- **Pocket Casts** (iOS/Android/Web)
- **Castro** (iOS)
- **Podcast Addict** (Android)
- **AntennaPod** (Android)

!!! tip "Private Feeds"
    RSS feed URLs contain a unique token. Don't share them publicly unless you want others to access your audiobooks!

## Managing Feeds

### Adding Books

To add books to an existing feed:

1. Go to **Library → My Feeds**
2. Click on the feed
3. Click **Edit**
4. Select additional books
5. Click **Save**

Podcast apps will automatically detect new episodes.

### Removing Books

1. Edit the feed
2. Deselect books to remove
3. Click **Save**

### Feed Settings

Each feed has:

- **Name** - Display name in podcast apps
- **Description** - Feed description
- **Books** - Which audiobooks to include

### Deleting Feeds

To delete a feed:

1. Go to **Library → My Feeds**
2. Click on the feed
3. Click **Delete Feed**
4. Confirm deletion

!!! warning
    Deleting a feed will break the subscription in podcast apps.

## Feed Updates

Feeds are updated automatically when:

- New books are added to the feed
- Books are removed from the feed
- Book metadata changes
- Audio files are downloaded

Podcast apps typically check for updates every few hours.

## Sharing Feeds

You can share feed URLs with other users:

1. Copy the RSS feed URL
2. Send it to the user
3. They add it to their podcast app

!!! warning "Security"
    Anyone with the RSS URL can access the audiobooks in that feed. Only share with trusted users.

## Troubleshooting

### Feed Won't Load

- Check that the audiobooks have been downloaded
- Verify the feed URL is correct
- Test the URL in a browser - it should show XML
- Check that Alima is accessible from the device

### Books Not Appearing

- Wait a few minutes for the podcast app to refresh
- Force refresh the feed in your app
- Verify books are added to the feed in Alima
- Check that audio files have been downloaded

### Playback Issues

- Ensure the audio file was fully downloaded
- Check file format compatibility with your app
- Try re-downloading the book in Alima

### Feed Shows Wrong Information

Feed metadata comes from:

- **Feed name** - Set when creating the feed
- **Episode titles** - Book titles from Audible
- **Descriptions** - Book descriptions from Audible
- **Cover art** - Book covers from Audible

To fix incorrect information:

1. Re-sync the Audible account
2. Edit the feed to refresh metadata
3. Force refresh in your podcast app

## Technical Details

RSS feeds conform to the Podcast RSS specification and include:

- Standard RSS 2.0 format
- iTunes podcast tags
- Enclosure tags for audio files
- Proper MIME types (audio/x-m4b)

The feed XML is generated dynamically on each request.
