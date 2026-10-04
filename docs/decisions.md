# Decisions

Why the bot is built the way it is, newest first. The current rules are in `docs/spec/`; this log only explains them. Add an entry when a decision changes a rule; do not repeat its date or history in the spec.

| Date | Decision | Why |
|------|----------|-----|
| 2026-10-04 | Requirements are traced by `@pytest.mark.req` markers and `tests/test_traceability.py`, not a Tests column. | The column had to be edited by hand on every change and drifted. |
| 2026-10-04 | The code-block (ANSI) reply format is removed; every table is an image. | Since the images, the code-block formatters only supplied header lines, yet cost code, golden files and documentation. |
| 2026-10-04 | Top cut: pairings of elimination rounds, `/cobra top-cut` and `/cobra bracket`, with Cobra's bracket templates copied from its source. Default `pairings` shows the latest round, Swiss or top cut. | The MVP replied "Top cut is not supported yet"; the export has no bracket format, so the templates are matched against the paired games. Cobra's separate bracket endpoint (937 KB for 235 players) is not used: one fetch per reply. |
| 2026-10-04 | Short ID names are keyed by the whole ID; IDs sharing the text before `:` add their initials (`HB PD`). | Several IDs of one faction (Haas-Bioroid, Jinteki, NBN, Weyland) showed the same short name. |
| 2026-10-03 | Standings, pairings and player search reply as PNG images (Pillow, bundled Noto Sans). | Code blocks looked different on desktop and mobile (mobile drops colours), forced 22/34-column layouts and could not show column headings. |
| 2026-10-03 | All image pages go in one message. | One upload instead of one per page cut a 5-image reply from 4.5–8 s. |
| 2026-10-03 | 60 rows per image (was 40). | The 145 tables of World Championship 2026 (290 rows) must fit in 5 pages. |
| 2026-10-03 | Drawn images cached 10 minutes under the hash of what they show. | Drawing is the slow part of a reply and unchanged data draws the same image. |
| 2026-10-03 | WorkerFunction 1769 MB; InteractionsFunction 512 MB. | At 256 MB the Worker took 20–26 s for the five images of a 262-player event and once timed out; the Interactions cold start took ~2.8 s, too close to Discord's 3 s. |
| 2026-10-03 | `/cobra player` is public (was ephemeral) and takes up to 10 names. | A group can follow its players together. |
| 2026-10-03 | Standings are "after round N" only for a round whose points Cobra's `matchPoints` already include. | Cobra recounts only when the organiser closes a round; a fully reported round can still be uncounted (World Championship 2026). |
| 2026-10-01 | Python 3.14 (Lambda `python3.14`). | The latest runtime Lambda supports. |
| 2026-10-01 | Shortcodes are resolved through Cobra's redirect and remembered in `codes/` without TTL. | Codes never change, and a remembered code still reaches the cache while the tournament is private (its redirect then hides the ID). |
| 2026-10-01 | A private tournament (401) serves the cached copy marked "now private". | Organisers hide a tournament briefly to announce results or protect Cobra; data fetched before hiding leaks nothing announced while hidden. |
| MVP | Two functions: InteractionsFunction acknowledges, WorkerFunction does the work. | A Function URL answers only when the invocation ends; fetching a large tournament can exceed Discord's 3 s limit. |
| MVP | Shared S3 cache, not per-instance `/tmp`. | Lambda scales out under load; a per-instance cache would let every instance fetch from Cobra, defeating the purpose. |
| MVP | Worker invoked asynchronously with no retries. | A retried Worker would post duplicate messages (NFR-06). |
