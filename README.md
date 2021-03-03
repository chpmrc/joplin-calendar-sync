# Joplin Google Calendar Sync

This tiny Python service uses Google Calendar and AWS S3's APIs to convert events to Joplin tasks.

It will only work if you use S3 as sync backend but it could be converted to use any storage service that exposes an API. E2EE is currently not supported (but should be easy to add).

# Setup

- Create OAuth credentials on the Google Console following [this guide](https://developers.google.com/calendar/quickstart/python), store project ID, Client ID and secret somewhere safe.
- `pip install -r requirements.txt`.
- Fill out `dotenv` with the required values, except `OAUTH_TOKEN_B64` (you can find the Joplin notebook's ID by clicking on a note/task and looking at the "parent's ID").
- Copy it as `.env` (if your runtime supports it) or simply `source dotenv`.
- Run `python gimme_token.py` to get the base64 encoded OAuth token and store it in `dotenv`/`.env`. Source it again.
- Run `python main.py`.

# Other environment variables

- `POLL_SECONDS`: how many seconds to wait between requests to Calendar's API (to fetch upcoming events).
- `LOOKAHEAD_SECONDS`: how many seconds in the future to look for events (starting from 00:00 of today).

# Notes

- It's advisable to keep `LOOKAHEAD_SECONDS` to a minimum (default is 60s) otherwise your event will keep being marked as not completed until it's due.
- It works with recurring events (since each instance has a separate ID).
- Supports Markdown in the event's description.
- Needs a first round of authentication with Google Calendar via browser.
- It was a half a weekend project to scratch my own itch, wasn't thinking of publishing but it could be useful to some. Code readability could use improvement.
