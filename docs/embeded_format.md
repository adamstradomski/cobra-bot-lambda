# Embed Format Requirements — Standings & Pairings

This document defines how the bot renders Cobra tournament data as Discord embeds.
The attached `standings_embed.json` and `pairings_embed.json` are **reference fixtures**
(expected output for the sample data). This document is the source of truth when the
fixtures and the text disagree.

Priorities: **MUST** / **SHOULD** / **COULD**. Unconfirmed decisions are marked **TBD**.

---

## 1. Common rules (both embeds)

| ID | Priority | Requirement |
|----|----------|-------------|
| C-1 | MUST | One message = one embed. Title = tournament name exactly as in Cobra. `url` = the tournament's Cobra page. |
| C-2 | MUST | Embed `color` = `0xE0B23A` (14725690). Defined as a single constant. |
| C-3 | MUST | Second description line: `Data from <t:{unix}:R>`, where `{unix}` = time the data was fetched from Cobra (not the message send time). Discord renders it in the viewer's locale (e.g. "3 minuty temu"). |
| C-4 | MUST | The table is a ` ```ansi ` code block. Every row ends with reset `\u001b[0m`. |
| C-5 | MUST | ANSI palette (no other codes): header `[1;37m`; rule, rank, SoS and losing player `[0;37m`; player (standings) and winning player `[1m` (bold, default color); neutral player (ID, no result) `[0m`; points/score `[1;33m`; Corp ID `[0;34m`; Runner ID `[0;35m`. **Never use `[30m`**: current Discord dark themes render it black on the code-block background (contrast ~1.5:1). `[37m` is not white: it renders dimmer than the default text, so it is the "secondary" color. See §1.2. |
| C-6 | MUST | Columns are aligned by **display width**, not by `len()`. Use `wcwidth` (or an equivalent); letters with diacritics (é, ā, Ō) are width 1, CJK and emoji are width 2. |
| C-7 | MUST | Player names longer than 16 columns are truncated to 15 columns plus `…`. |
| C-8 | MUST | Backticks in player names are replaced with `'` so they cannot close the code block. |
| C-9 | MUST | Send with `allowed_mentions: {"parse": []}`. Names such as `@Bookkeeper` must never ping anyone. |
| C-10 | MUST | Never send the `username` field from the fixtures in slash-command responses: it only works for webhooks. |
| C-11 | MUST | Discord limits: description ≤ 4096, field value ≤ 1024, ≤ 25 fields, all text in an embed ≤ 6000. A unit test checks every rendered fixture against these limits. |
| C-12 | MUST | Chunking: rows go into the description until the next row would exceed the limit. The remaining rows go into fields named `\u200b` (zero-width space), each a separate ` ```ansi ` block. The header row appears only in the first block. A table row (in pairings, both lines of a table) is never split. |
| C-13 | MUST | If the total exceeds 6000 characters, split the output into further messages or embeds. **TBD:** a follow-up message vs. pagination with buttons vs. a `top N` / `page` option on the command. |
| C-14 | MUST | Empty states: tournament not found, no rounds yet, round has no pairings. Each is a short embed with a single sentence and no code block. Wording: **TBD**. |
| C-15 | SHOULD | Rendering is a pure function `(tournament data, fetched_at) -> embed dict` with no I/O, covered by golden-file tests against the fixtures. |
| C-16 | COULD | Narrow layout for mobile (the 52-column table wraps on phones). **TBD:** whether this is needed. |

### 1.1 Identity abbreviations

| ID | Priority | Requirement |
|----|----------|-------------|
| A-1 | MUST | Corp and Runner IDs are shown in short form, at most 9 columns, from a mapping kept in one data file (e.g. `id_short_names.json`), not hard-coded in the renderer. |
| A-2 | MUST | Fallback for an ID missing from the mapping. Runner: the nickname in quotes if present (`René "Loup" Arcemont` → `Loup`), otherwise the first word. Corp: the full name. In both cases, truncate to 9 columns with `…`, and log a warning that the ID is missing from the mapping. |
| A-3 | MUST | Initial mapping (from the sample data):<br>Corp — Nuvem SA→Nuvem, Méliès U→Méliès, Nebula Talent Management→Nebula, Haas-Bioroid→HB, AU Co.→AU Co., Weyland Consortium→Weyland, Ob Superheavy Logistics→Ob, Editorial Division→Editorial, The Zwicky Group→Zwicky, BANGUN→BANGUN, Issuaq Adaptics→Issuaq, Earth Station→Earth St., Synapse Global→Synapse.<br>Runner — Arissana Rocha Nahu→Arissana, Sebastião Souza Pessoa→Sebastião, MuslihaT→MuslihaT, René "Loup" Arcemont→Loup, Esâ Afontov→Esâ, Magdalene Keino-Chemutai→Magdalene, Ryō "Phoenix" Ōno→Phoenix, Lat→Lat, Dewi Subrotoputri→Dewi, Az McCaffrey→Az, Mercury→Mercury, Zahya Sadeghi→Zahya, Captain Padma Isbister→Padma, Barry "Baz" Wong→Baz. |
| A-4 | MUST | A player with no deck or ID registered is shown as `—`. |
| A-5 | SHOULD | Before shortening, normalize the ID to the part before `:`. Cobra may return `Nuvem SA: Law of the Land`. **TBD:** confirm the exact API format. |

### 1.2 Measured Discord ANSI rendering (desktop, dark theme, 2026-10)

Measured from a screenshot of the live bot. The code-block background is `#282939`.

| Code | Rendered | Contrast | Use |
|------|----------|----------|-----|
| `[30m` | `#000000` | 1.5:1 | forbidden |
| `[37m` | `#B6B7BC` | 7.2:1 | secondary text |
| default (`[0m`/`[1m`) | ≈`#DBDEE1` (**TBD**: measure) | ≈10.6:1 | primary text |
| `[33m` | `#B36C00` | 3.5:1 | points |
| `[34m` | `#1B73D5` | 3.0:1 | Corp |
| `[35m` | `#D53FAE` | 3.5:1 | Runner |

Discord's 8 ANSI colors cannot be customized and differ between themes (light, dark, onyx). **TBD**: check the light theme and `[36m` (cyan) as a possibly brighter Corp color.

---

## 2. Standings embed

Description:
```
**Standings after round {n}**
Data from <t:{unix}:R>
```ansi
<table>
```
```

| ID | Priority | Requirement |
|----|----------|-------------|
| S-1 | MUST | Columns and widths: rank right-aligned in 2 + 2 spaces · player 16 · points right-aligned in 3 + 2 spaces · SoS (3 decimal places) + 2 spaces · Corp 10 · Runner (no padding). Header: ` #  Player            Pts  SoS    Corp      Runner`, followed by a `─` rule of header width + 3. |
| S-2 | MUST | Rank 100+: the rank column widens to 3 for the whole table, and the header shifts with it. |
| S-3 | MUST | Row order and rank exactly as returned by Cobra. The bot does not compute tiebreakers itself. |
| S-4 | MUST | One empty line between groups with different point totals. The first row is never preceded by an empty line, including at the start of a chunk. |
| S-5 | MUST | Footer: `Round {n} · {count} players · Pts / SoS / Corp / Runner`. |
| S-6 | SHOULD | Dropped players: **TBD** whether to hide them, append them at the end, or mark them (e.g. with a `(drop)` suffix). |
| S-7 | COULD | Extended SoS (eSoS) column. **TBD.** |

## 3. Pairings embed

Description:
```
**Round {n} pairings — complete|in progress**
-# Top cut in progress — not supported yet      ← only when Cobra reports a top cut
Data from <t:{unix}:R>
```ansi
<table>
```
```

| ID | Priority | Requirement |
|----|----------|-------------|
| P-1 | MUST | Two lines per table. Line 1: `T{n}` padded to 4 · Corp player 16 · score (right-aligned in 4, padded to 6) · Runner player. Line 2: 4 spaces · Corp ID padded to 22 · Runner ID. Header: `T   Corp            Score Runner`, followed by a 44-column rule. |
| P-2 | MUST | **Normalize sides:** Corp is always on the left and Runner on the right, whatever order Cobra uses. When the original order was Runner-first, reverse the score (`0–3` → `3–0`). |
| P-3 | MUST | Scores use an en dash `–` (U+2013). The score is always from the Corp's point of view. Footer: `Round {n} · {count} tables · Corp left, Runner right · score from Corp side`. |
| P-4 | MUST | Coloring: the winner is bold white, the loser grey. ID and draws: both players neutral `[0;37m`, score shown as `ID`. |
| P-5 | MUST | Status `complete` when every table has a result, otherwise `in progress`. A table without a result: score `vs`, both players neutral. |
| P-6 | MUST | Bye: line 1 `T{n}  {player}  BYE`; line 2 shows that player's deck. Sides: **TBD** (which ID to show). |
| P-7 | MUST | Unknown sides (Cobra provides none): no normalization, original order, both IDs shown in grey. |
| P-8 | MUST | The top-cut line appears only when the tournament has entered the cut phase. Top-cut rendering is out of scope (MVP). |
| P-9 | SHOULD | Other score formats (double-sided `6–0`, `3–3`, `0–6`; modified wins; unknown formats) are shown verbatim. Winner coloring applies only when one side clearly has more points. |
| P-10 | SHOULD | Table numbers as in Cobra. Order: ascending table number. |

## 4. Acceptance criteria (tests)

1. Rendering the sample data (standings, round 8, 46 players) produces an embed identical to `standings_embed.json` (ignoring `username` and the `<t:…>` value).
2. Same for pairings (23 tables) against `pairings_embed.json`.
3. Normalization: `Inermis (Runner) 0–3 Minstrel (Corp)` renders as `Minstrel 3–0 Inermis`, with Minstrel bold white.
4. A name `` a`b `` renders as `a'b`. A 20-character name is truncated to 15 characters plus `…`. A name with an emoji keeps the following columns aligned (verified by display width).
5. 60 generated players: no embed exceeds any limit from C-11. Splitting follows C-12 and C-13.
6. An ID missing from the mapping triggers the fallback (A-2) and a log warning.
7. The standings table has an empty line exactly at each change in point total. No chunk starts with an empty line.

## 5. Open questions (TBD)

- Output larger than 6000 characters: follow-up message vs. pagination vs. a command option (C-13).
- Dropped players in standings (S-6).
- Which ID to show for a bye (P-6).
- Exact Cobra API format for IDs, results, byes and top cut (A-5, P-5–P-9).
- Wording of empty-state messages (C-14).
- Whether a mobile layout is needed (C-16).
