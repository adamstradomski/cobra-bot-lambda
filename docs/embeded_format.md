# Embed Format Requirements — Standings & Pairings (v2, compact)

This document defines how the bot renders Cobra tournament data as Discord embeds.

**Reference fixtures** (expected output for the sample data; the `<t:…>` value and `url` are placeholders):

- `standings_embed.json`: Mistrzostwa Polski 2026, standings after round 8 (46 players).
- `pairings_embed.json`: same tournament, round 8 pairings, single-sided (23 tables).
- `pairings_dss_embed.json`: 12 Ogólnopolska Liga Netrunnera, round 3, double-sided, in progress (8 tables).
- `pairings_dss_round2_t1_embed.json`: same league, round 2, table 1 only, double-sided, complete.

These design fixtures hold real player names, so they are not committed. The repository checks the same layout with golden files built from the anonymised fixtures (`tests/golden/`, see §5).

This document is the source of truth when it disagrees with the fixtures.

Priorities: **MUST** / **SHOULD** / **COULD**. Unconfirmed decisions are marked **TBD**. Where `docs/findings.md` answers a TBD, the requirement says so.

**Changes from v1:** the bot cannot tell whether a viewer is on desktop or mobile, so v2 uses **one compact format for both** (this replaces v1's 52-column table and its open question about a mobile layout):

- Every table line is at most **34 display columns**, so it fits a phone screen.
- The table stays readable when the mobile client drops ANSI colors.
- Colors are a desktop-only enhancement.
- Standings show IDs on a second line; pairings show the points each player scored instead of a score from the Corp's side, and have no column header.
- Double-sided pairings show the two games as columns instead of `↳` lines.

---

## 1. Common rules

| ID | Priority | Requirement |
|----|----------|-------------|
| C-1 | MUST | One message = one embed. Title = tournament name exactly as in Cobra. `url` = the tournament's Cobra page. |
| C-2 | MUST | Embed `color` = `0xE0B23A` (14725690). Defined as a single constant. |
| C-3 | MUST | Description starts with a bold status line (e.g. `**Standings after round 8**`) and ends its header with `Data from <t:{unix}:R>`, where `{unix}` = time the data was fetched from Cobra (not the message send time). Discord renders it in the viewer's locale (e.g. "3 minuty temu"). |
| C-4 | MUST | The table is one ` ```ansi ` code block. No column-header row in pairings. Standings have a header (§2). |
| C-5 | MUST | **Width:** every table line is ≤ 34 display columns (measured without ANSI codes, with `wcwidth` or an equivalent; CJK and emoji count as 2). A unit test enforces this on every fixture. Columns are aligned by display width, not by `len()`: letters with diacritics (é, ā, Ō) are width 1, combining marks width 0. |
| C-6 | MUST | **Readable without color:** no information may depend on color alone. On mobile, ANSI codes are stripped and everything renders in one color. Winners are recognizable from the points shown next to the name; sides are recognizable from position or the `C`/`R` tag. |
| C-7 | MUST | Player names longer than 15 columns are truncated to 14 columns plus `…` (the longest real sample, `nervousnightjar`, is exactly 15). Backticks in names are replaced with `'` so they cannot close the code block. |
| C-8 | MUST | Send with `allowed_mentions: {"parse": []}`. Names such as `@Bookkeeper` must never ping anyone. Never send `username` (webhook-only). |
| C-9 | MUST | Discord limits: description ≤ 4096, field value ≤ 1024, ≤ 25 fields, all text in an embed ≤ 6000. A unit test checks every fixture against these limits. |
| C-10 | MUST | **Chunking:** whole units (a standings player = 2 lines, a pairings table = 2 or 4 lines) go into the description until the next unit would exceed the limit. The remaining units go into fields named `​` (zero-width space), each its own ` ```ansi ` block. The standings header appears only in the first block. A unit is never split, and a block never starts with an empty line. |
| C-11 | MUST | If one embed exceeds 6000 characters (about 60+ players in standings), split the output across further messages. **TBD:** a follow-up message vs. pagination with buttons vs. a command option. *Current behaviour (SPEC §9):* follow-up messages, at most 5; if that is not enough, the longest prefix of units is kept and the last line reads "…and N more — [full list on Cobra](url)". |
| C-12 | MUST | Empty states (tournament not found, no rounds yet, no pairings): a short embed with a single sentence and no code block. Wording: **TBD** (current wording in `messages.py`). |
| C-13 | SHOULD | Rendering is a pure function `(tournament data, fetched_at) -> embed dict`, covered by golden-file tests against the fixtures. |
| C-14 | MUST | No decorative glyphs (`↳`, arrows, emoji) in the table. Scores use the en dash `–` (U+2013), never `-`. Separator between name and ID: ` · ` (U+00B7). |

### 1.1 ANSI palette

Measured on Discord desktop, dark theme (2026-10), from a screenshot of the live bot. The code-block background is `#282939`.

| Role | Codes | Renders as | Contrast |
|------|-------|-----------|----------|
| Primary text (rank, table no., neutral player) | `[0m` | ≈`#DBDEE1` (**TBD**: measure) | ≈10.6:1 |
| Player in standings, round/game winner | `[0m` + `[1m` (bold, default color) | ≈`#DBDEE1` bold | ≈10.6:1 |
| Secondary (header, rule, SoS, loser, `·`, unknown ID `—`) | `[0;37m` | `#B6B7BC` | 7.2:1 |
| Points / score | `[1;33m` | `#B36C00` | 3.5:1 |
| Corp ID, `C` tag | `[0;34m` | `#1B73D5` | 3.0:1 |
| Runner ID, `R` tag | `[0;35m` | `#D53FAE` | 3.5:1 |
| *Forbidden* | `[30m` | `#000000` | 1.5:1 |

Discord's 8 ANSI colors cannot be customized and differ between themes (light, dark, onyx). **TBD:** check the light theme, and `[36m` (cyan) as a possibly brighter Corp color.

| ID | Priority | Requirement |
|----|----------|-------------|
| A-0 | MUST | **Never use `[30m`**: it renders black (~1.5:1 contrast). `[37m` is dimmer than default text, so it serves as the secondary color. `[1m` keeps the previous color, so "bold default" is always emitted as `[0m[1m`. **TBD:** whether `[0;1m` works as a single code. Every line ends with `[0m`. No other codes are used. |

### 1.2 Identity abbreviations

| ID | Priority | Requirement |
|----|----------|-------------|
| A-1 | MUST | IDs are shown in short form (≤ 9 columns) from a mapping in one data file (`src/cobra_bot/formatting/identities.py`), not hard-coded in the renderer. |
| A-2 | MUST | Fallback for an unmapped ID. Runner: the nickname in quotes if present (`René "Loup" Arcemont` → `Loup`), otherwise the first word. Corp: the part before `:`. In both cases, truncate to 9 columns with `…` and log a warning. |
| A-3 | MUST | Initial mapping:<br>Corp — Nuvem SA→Nuvem, Méliès U→Méliès, Nebula Talent Management→Nebula, Haas-Bioroid→HB, AU Co.→AU Co., Weyland Consortium→Weyland, Ob Superheavy Logistics→Ob, Editorial Division→Editorial, The Zwicky Group→Zwicky, BANGUN→BANGUN, Issuaq Adaptics→Issuaq, Earth Station→Earth St., Synapse Global→Synapse, GameNET→GameNET.<br>Runner — Arissana Rocha Nahu→Arissana, Sebastião Souza Pessoa→Sebastião, MuslihaT→MuslihaT, René "Loup" Arcemont→Loup, Esâ Afontov→Esâ, Magdalene Keino-Chemutai→Magdalene, Ryō "Phoenix" Ōno→Phoenix, Lat→Lat, Dewi Subrotoputri→Dewi, Az McCaffrey→Az, Mercury→Mercury, Zahya Sadeghi→Zahya, Captain Padma Isbister→Padma, Barry "Baz" Wong→Baz, Omission→Omission.<br>GameNET is confirmed: the fixtures show Cobra returns `GameNET` before the `:`. **TBD:** the fixtures show `Hiram "0mission" Svensson` (with a zero), not `Omission`; the A-2 fallback renders it `0mission`. Confirm whether to map it, and to what. |
| A-4 | MUST | An unknown or unregistered ID is shown as `—` in the secondary color. |
| A-5 | SHOULD | Before shortening, normalize the ID to the part before `:` (Cobra returns e.g. `Nuvem SA: Law of the Land`). |

---

## 2. Standings

```
 # Player          Pts  SoS
─────────────────────────────
 1 davz131          22  1.821
   Nuvem · Arissana

 2 Matuszczak       18  2.000
   Méliès · Sebastião
 3 Kris_Casual      18  1.734
   Nebula · Arissana
```

| ID | Priority | Requirement |
|----|----------|-------------|
| S-1 | MUST | Line 1: rank right-aligned in 2 + space · player padded to 16 · points right-aligned in 3 · 2 spaces · SoS (3 decimal places). Line 2: 3 spaces · `Corp · Runner` (short IDs). |
| S-2 | MUST | Header ` # Player          Pts  SoS` plus a `─` rule (header width + 2, i.e. as wide as a row: 29), both secondary. Colors: rank primary, player bold, points yellow, SoS secondary, Corp blue, `·` secondary, Runner pink. |
| S-3 | MUST | Rank 100+: the rank column widens to 3 for the whole table (header, rule and the indent of line 2 shift with it). |
| S-4 | MUST | Order and rank exactly as returned by Cobra. No tiebreakers are computed. |
| S-5 | MUST | One empty line between groups with different point totals. No empty line inside a group. |
| S-6 | MUST | Footer: `Round {n} · {count} players · Corp · Runner on 2nd line` (no round part before the first round is complete). |
| S-7 | SHOULD | Dropped players: **TBD** whether to hide them, append them at the end, or mark them. |
| S-8 | COULD | Extended SoS (eSoS) column. **TBD.** |

## 3. Pairings

Header: `**Round {n} pairings — complete|in progress**`. When Cobra reports a top cut, add `-# Top cut in progress — not supported yet` (top cut rendering is out of scope). One empty line between tables.

| ID | Priority | Requirement |
|----|----------|-------------|
| P-1 | MUST | Status is `complete` when every game has a result, otherwise `in progress`. |
| P-2 | MUST | Points shown are the **points the player scored** (`3`, `0`, or any other value Cobra reports, as is), right-aligned in 2 and colored yellow. `ID` = intentional draw. `–` = no result yet. A player with more points is bold; with fewer, secondary; equal or no result, primary. |
| P-3 | MUST | Table label `T{n}` padded to 4, primary, on the first line of a table only. Following lines are indented with 4 spaces. From table 100 the label column widens for the whole round. |
| P-4 | MUST | Bye: `T{n}  BYE {player} · {id}`, a single line. **TBD:** which ID to show. Note that a 15-column name and a 9-column ID make this line 35 columns, one over C-5. *Current behaviour:* no ID, `T{n}  BYE {player}`. |
| P-5 | MUST | How to detect a single-sided vs. a double-sided round. *Answered by findings Q3:* a pairing is double-sided when neither seat has a role (a Corp/Runner role exists only in single-sided games); detected per pairing. |
| P-6 | SHOULD | Table order: ascending table number, as in Cobra. |

### 3.1 Single-sided (SSS): 2 lines per table

```
T1   3 davz131 · Nuvem
     0 Matuszczak · Sebastião

T2  ID Suipe · Nuvem
    ID gruntownie · Loup
```

| ID | Priority | Requirement |
|----|----------|-------------|
| SS-1 | MUST | **Corp is always line 1, Runner line 2**, whatever order Cobra uses. Colors: Corp ID blue, Runner ID pink. |
| SS-2 | MUST | Line: label/indent (4) · points (2) · space · player · ` · ` · short ID. Longest line: 4 + 2 + 1 + 15 + 3 + 9 = 34 columns. |
| SS-3 | MUST | Footer: `Round {n} · {count} tables · Corp first · number = points scored`. |

### 3.2 Double-sided (DSS): 4 lines per table

```
T1   3 Kris_Casual
      C GameNET   0  R Omission  3
     3 Matuszczak
      R —         3  C —         0
```

| ID | Priority | Requirement |
|----|----------|-------------|
| DS-1 | MUST | Per player: a name line (label/indent · round total in 2 · space · player) and a game line. |
| DS-2 | MUST | **Game line columns = games:** the left column is game 1 and the right column is game 2. Player 1 (Corp in game 1) is shown `C … R …`, player 2 is shown **`R … C …`** (reversed), so each column pairs the opponents' decks from the same game. |
| DS-3 | MUST | Game cell: tag `C`/`R` + space + short ID padded to 10 + points scored in that game (`3`, `0`, `–`). Line: 6 spaces · cell · 2 spaces · cell = 34 columns. Tag and ID in side color (unknown ID `—` secondary), points yellow. |
| DS-4 | MUST | Round total = sum of the player's points in both games (e.g. 0 + 3 = 3). `–` when neither game has a result; when only one has, the total is that game's points. |
| DS-5 | MUST | Player 1 = the player who is Corp in game 1. *Answered by findings Q3:* each seat holds its own Corp and Runner results, and game 1 is seat 1 as Corp against seat 2 as Runner, so player 1 is seat 1. |
| DS-6 | MUST | Footer: `Round {n} · {count} tables · double-sided · columns = game 1 | game 2` (when any table of the round is double-sided). |

## 4. Player cards (`/cobra player`)

Not covered by the design fixtures; derived from §2 and §3 so the same rules (C-5 width, C-6, palette) hold.

- A card is the player's standings unit (§2, without the header), a secondary `Round {n}` line and the player's table in the latest Swiss round in the §3 form (including a bye), or `Round {n}: not paired`. Cards are separated by an empty line.
- Footer: `Corp · Runner on 2nd line · pairing: Corp first · number = points scored`.

## 5. Acceptance criteria (tests)

1. Rendering the sample data reproduces each fixture exactly (ignoring `url` and the `<t:…>` value). *In the repository:* golden files for the anonymised `single_sided_top8` and `dss` fixtures (`tests/formatting/test_golden.py`).
2. No table line in any fixture exceeds 34 display columns once ANSI codes are removed.
3. All fixtures satisfy the C-9 limits. 60 generated players trigger the split described in C-11.
4. With ANSI codes removed, every winner is identifiable from the points alone, and every DSS deck from the `C`/`R` tag alone.
5. SSS: `Inermis (Runner) 0–3 Minstrel (Corp)` renders Minstrel on line 1 with `3` (bold) and Inermis on line 2 with `0` (secondary).
6. DSS: Kris_Casual (C GameNET) 0–3 Matuszczak (R —), then Matuszczak (C —) 0–3 Kris_Casual (R Omission), renders exactly the 4 lines from §3.2.
7. DSS with no results: all points are `–`, and both players are primary and not bold.
8. Output contains no `[30m`, no `↳`, and no `-` in scores. Every line ends with `[0m`.
9. A name `` a`b `` renders `a'b`. A 20-character name is truncated to 14 characters plus `…`. A name with an emoji does not break the 34-column limit.
10. An unmapped ID uses the A-2 fallback and logs a warning.
11. The standings table has an empty line exactly at each change in point total. No chunk starts with an empty line.

## 6. Open questions (TBD)

- Output larger than 6000 characters (C-11).
- Exact default text color and whether `[0;1m` works (§1.1). Light theme readability of the palette; `[36m` for Corp.
- Dropped players (S-7). eSoS (S-8).
- Which ID to show for a bye, and how to keep that line within 34 columns (P-4).
- Whether and how to map `Hiram "0mission" Svensson` (A-3).
- Exact Cobra API format for results and top cut beyond what `docs/findings.md` answers.
- Wording of empty states (C-12).
