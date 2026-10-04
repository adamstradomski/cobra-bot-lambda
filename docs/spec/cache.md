# Cache (S3)

Code: `cobra/cache.py` (logic over the `CacheStore` protocol, in-memory store for tests), `cobra/s3_store.py`, `image_cache.py`. One private bucket from the SAM template; a lifecycle rule deletes every object after 1 day. TTLs and stale behaviour are a contract: do not change them without asking.

## Tournament data: `cache/{id}.json`

- The raw Cobra JSON; object metadata `fetched-at` (UTC epoch).
- Fresh (age ≤ 60 s): served without contacting Cobra.
- Expired or missing: fetched from Cobra, written to S3, served.
- Fetch failure (`Unavailable`): the cached copy is served marked stale, at any age, with the notice "Cobra unavailable — data from <t:UNIX:R>". No copy → "Cobra is unavailable, try again later."
- `NotFound` → "Tournament not found."; nothing is cached.
- `Private` (401): the cache entry is **not** overwritten; the cached copy is served marked stale, at any age (up to the 1-day lifecycle), with "Tournament is now private — data from <t:UNIX:R>". No copy → "This tournament is private."

## Shortcodes: `codes/{CODE}.json`

- Shortcode → tournament ID, written whenever a shortcode resolves to `/tournaments/{id}`. Codes never change, so there is no TTL beyond the bucket lifecycle; every successful resolution refreshes it.
- When a shortcode redirects to `/` (private tournament), the code is looked up here: a hit continues with that ID (the private rules above apply); a miss replies "This tournament is private."

## Single-flight: `locks/{id}`

- Before fetching, the Worker creates `locks/{id}` with a conditional write (`If-None-Match: *`) holding a timestamp. The winner fetches, then deletes the lock.
- The others poll up to 2 s for a fresh cache object, then serve stale data if there is any, else fetch themselves.
- A lock older than 15 s is abandoned and replaced (conditional on its ETag).

## Drawn images: `images/{sha256}.png`

- Kept **10 minutes**, separate from the 60 s data cache: drawing is the slow part of a reply, and unchanged data draws the same image.
- The key hashes exactly what the image shows: cells, columns, colours, layout constants, the font files, and `RENDER_VERSION` (`formatting/image.py`, `formatting/bracket_image.py`). Bump `RENDER_VERSION` when the drawing changes in a way those do not show.
- The embed text around an image (header, data age) is built fresh every time.
- A failed read counts as a miss; a failed write is logged. Neither blocks the reply.
