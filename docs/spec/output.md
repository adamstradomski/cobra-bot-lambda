# Output: replies, images, short ID names

Code: `formatting/image.py` (tables, pages), `formatting/bracket_image.py`, `formatting/header.py` (embed text), `formatting/embed.py`, `formatting/text.py`, `formatting/identities.py` (generated), `messages.py` (every user-facing string; the exact wording lives there, not here).

## Reply types

- **Image reply** (pairings, standings, top cut, bracket, player search with a match): one message with one embed and one PNG per page, in place of the deferral.
- **Embed without an image**: player search with no match: the header and notes, no footer.
- **Text reply**: errors and states with nothing to show ("Tournament not found.", "Tournament has not started yet.", …): one embed with one sentence.
- Every message: embed colour `0xE0B23A`, `allowed_mentions: {"parse": []}`.

## Embed text

- First page: title = the tournament name (plain text; Discord does not render markdown there), title link = the tournament on Cobra (standings and top cut: the standings page; bracket: the bracket page).
- Description of the first page: the state line in bold (e.g. "**Round 5 pairings — in progress**", "**Standings after round 8**", "**Top cut round 6 pairings — complete**", "**Top 8 cut — finished**"); for standings, the cut note as subtext (`-#`) once Swiss is over; then "Data from <t:UNIX:R>" or the stale notice (`docs/spec/cache.md`). Notes follow (player search). The timestamp sits in the description because footers do not render Discord timestamps.
- Later pages: no title, no description.
- Footer of every page: a short legend ("Round 8 · 46 players", "Round 8 · 23 tables", "Round 9 · 4 games", "Top 8 · 8 players · W–L = games won and lost", "15 games · bold = winner"), plus "N / M" when there are several pages.

## Pages

- At most 60 rows per image (145 tables = 290 rows fit in 5 pages); at most 5 pages, all in one message (Discord allows 10 embeds and attachments per message).
- Standings, top cut and player rows fill every page (a points group may continue on the next one); a pairing is never split.
- Past 5 pages the rest is dropped and the last description ends with "…and N more — [full list on Cobra](url)", N counting players or tables.
- Text in an image cannot be selected; the Cobra link gives the selectable version.

## Tables

| Reply | Columns |
|-------|---------|
| Standings | `#`, Player, Corp, Runner, Pts, SoS (three decimals). A background stripe per group of players on equal points. |
| Pairings, single-sided | Table, Player, Side, ID, Pts. Two rows per table, the Corp first. |
| Pairings, double-sided | Table, Player, Game 1 (`C`/`R` tag + ID), points, Game 2, points, Total. Seat 1 (the Corp in game 1) first. |
| Pairings, top cut | Game, Player, Side, ID, W/L. Two rows per game, the Corp first; `W` / `L`, `–` while unreported. |
| Top cut | `#` (blank while Cobra has not decided the place), Player, Corp, Runner, W–L (games won and lost in the cut), Seed. Players still in bold with a bold W–L, players out secondary. |
| Player search | `#`, Player, Corp, Runner, Pts, SoS, then the latest round (heading `Round N`): the table (`T6`) or game (`G13`), the side (`Corp`/`Runner` in its colour; double-sided `C 3 · R 0`), the opponent, the score from the player's side (`3 – 0`; top cut `W` / `L`; `–`, `ID`, `BYE`, `not paired`). Before any round only the standings columns. |

- A bye: `BYE` in the third column. An intentional draw: `ID` as the points of both players.
- Winners bold, losers secondary; equal points, an intentional draw or no result leave both plain. Standings names and points bold.
- Alternate groups get a background stripe: a points group (standings), a table (pairings).
- Names cut at 28 characters with `…`; an unknown player ID shows "Unknown player".

## Bracket image

- Laid out like Cobra's bracket page: a column per bracket round; double elimination `Upper bracket` above `Lower bracket`, single elimination one unlabelled section.
- Each game a rounded box with its number on the left; a line from each game to the game its winner plays next in the same section. The first column is evenly spaced; a later game is centred between the games feeding it.
- A slot: the player's name (cut at 18 characters with `…`) and, once paired, the short ID of the side played, in its colour, right-aligned. Winner bold, loser secondary, unreported plain. An unknown player: `Seed N`, `Winner of G`, `Loser of G` or `TBD` (single elimination, decided when paired), secondary. No faction logos, no pronouns.
- The second final of double elimination appears only once Cobra pairs it.

## Look

- Discord's dark theme: background `#2b2d31`, stripe `#313338`, rule `#3f4147`, text `#dbdee1`, secondary `#949ba4` (SoS, losers, headings, unknown ID), points `#f0b232`, Corp `#7998ec`, Runner `#dd4847` (NSG card-back colours, the blue lightened).
- Bundled Noto Sans Regular/Bold (SIL OFL, `src/cobra_bot/fonts/`): Lambda has no system fonts, and Pillow's built-in font lacks Latin Extended letters. Drawn at twice the display size.
- Only the Worker imports Pillow; InteractionsFunction must answer within 3 s (`tests/handlers/test_import_cost.py`).

## Safe text

- Player names and IDs drawn in images: backticks become `'`, control and format characters are dropped, whitespace runs collapse to one space, NFC-normalised (`text.code_text`).
- User text in message text (the search query in the header and notes): a backslash before each of `` \ * _ ~ ` | > # - [ ] ( ) < : ``; whitespace runs, newlines included, collapse to one space (`text.escape_markdown`).
- Names never appear in message text except the query the user typed.

## Short ID names

| ID | Rule |
|----|------|
| A-1 | IDs are shown by a short name of at most 9 columns, from the generated map `formatting/identities.py` (separate Corp and Runner maps, keyed by the whole ID; `uv run scripts/generate_identities.py` rebuilds it from NetrunnerDB). |
| A-2 | An ID missing from the map: the prefix's short name from the prefix maps in the same file (`Haas-Bioroid` → `HB`), else — Corp: the text before the `:`; Runner: a quoted nickname if there is one (`René "Loup" Arcemont` → `Loup`), otherwise the first word — cut to 9 columns with `…`. A warning is logged once per ID and process. |
| A-3 | Hand-picked names (overrides in `scripts/generate_identities.py`), e.g. Nuvem SA → Nuvem, Haas-Bioroid → HB, Weyland Consortium → Weyland, Earth Station → Earth St., Arissana Rocha Nahu → Arissana, Hiram "0mission" Svensson → 0mission. |
| A-4 | A missing or blank identity shows `—` in the secondary colour. |
| A-5 | The short name comes from the text before the first `:` (Cobra sends e.g. `Nuvem SA: Law of the Land`). IDs that share that text add their initials: `HB PD`, `Jnt RH`, `NBN MN`, `NBN R+`, `Wey BtL`. |
