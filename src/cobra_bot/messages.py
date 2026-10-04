"""All user-facing text (FR-17: English). Nothing else in the code base builds
sentences shown to Discord users; formatters only fill these templates."""

# --- errors (FR-16, FR-21) -------------------------------------------------------

INVALID_REFERENCE = (
    "Invalid tournament reference. Use a Cobra tournament ID, a Cobra link or a "
    "shortcode."
)
TOURNAMENT_NOT_FOUND = "Tournament not found."
TOURNAMENT_PRIVATE = "This tournament is private."
COBRA_UNAVAILABLE = "Cobra is unavailable, try again later."
NOT_STARTED = "Tournament has not started yet."
NO_TOP_CUT = "This tournament has no top cut on Cobra yet."
NO_PLAYERS_MATCH = "No players match."
UNKNOWN_COMMAND = "Unknown command."
INTERNAL_ERROR = "Something went wrong. Please try again later."
COBRA_DATA_UNREADABLE = "Cobra returned data the bot cannot read."


def bracket_unavailable(size: int) -> str:
    return f"There is no bracket for a top {size} cut."


def round_out_of_range(requested: int, last_round: int) -> str:
    return (
        f"Round {requested} does not exist. This tournament has rounds 1–{last_round}."
    )


# --- headers and notes (SPEC §9) -------------------------------------------------

NO_COMPLETED_ROUNDS = "No completed rounds yet"
REGISTERED_PLAYERS = "Registered players — not started yet"
IN_PROGRESS = "in progress"
COMPLETE = "complete"


def pairings_header(round_number: int, complete: bool) -> str:
    state = COMPLETE if complete else IN_PROGRESS
    return f"Round {round_number} pairings — {state}"


def cut_pairings_header(cut_round: int, complete: bool) -> str:
    state = COMPLETE if complete else IN_PROGRESS
    return f"Top cut round {cut_round} pairings — {state}"


def standings_header(after_round: int) -> str:
    return f"Standings after round {after_round}"


# The top cut's state (domain.bracket.CutStatus).
CUT_STATES = {
    "announced": "announced — not started yet",
    "in_progress": "in progress",
    "finished": "finished",
}
SEE_TOP_CUT = "see `/cobra top-cut` and `/cobra bracket`"
NO_TOP_CUT_YET = "No top cut on Cobra yet"


def cut_note(status: str, size: int) -> str:
    """The top cut's state under the standings once Swiss is over."""
    if status == "none":
        return NO_TOP_CUT_YET
    note = f"Top {size} cut {CUT_STATES[status]}"
    return note if status == "announced" else f"{note} — {SEE_TOP_CUT}"


def top_cut_header(size: int, status: str) -> str:
    return f"Top {size} cut — {CUT_STATES[status]}"


def bracket_header(size: int, double: bool, status: str) -> str:
    kind = "double elimination" if double else "single elimination"
    return f"Top {size} bracket ({kind}) — {CUT_STATES[status]}"


def players_header(query: str) -> str:
    """`query` must already be escaped for Discord markdown."""
    return f"Players matching “{query}”"


def data_from(timestamp: str) -> str:
    return f"Data from {timestamp}"


def stale_cobra_unavailable(timestamp: str) -> str:
    return f"Cobra unavailable — data from {timestamp}"


def stale_tournament_private(timestamp: str) -> str:
    return f"Tournament is now private — data from {timestamp}"


def player_round(round_number: int) -> str:
    """Label above a player's pairing in the given round."""
    return f"Round {round_number}"


def player_not_paired(round_number: int) -> str:
    return f"Round {round_number}: not paired"


def more_players_matched(count: int) -> str:
    return f"…and {count} more matched"


def more_players_named(count: int, name: str) -> str:
    """`name` must already be escaped for Discord markdown."""
    return f"…and {count} more matched “{name}”"


def no_player_named(name: str) -> str:
    """`name` must already be escaped for Discord markdown."""
    return f"No players match “{name}”."


def names_skipped(count: int, limit: int) -> str:
    return f"Only the first {limit} names were searched ({count} more given)."


def omitted_entries(count: int, url: str) -> str:
    return f"…and {count} more — [full list on Cobra]({url})"


# --- entry vocabulary -----------------------------------------------------------

BYE = "BYE"
WIN = "W"  # a top-cut game's result
LOSS = "L"
INTENTIONAL_DRAW = "ID"
NO_RESULT = "–"  # points not reported yet
CORP_TAG = "C"  # the side of a double-sided game
RUNNER_TAG = "R"
UNKNOWN_IDENTITY = "—"
UNKNOWN_PLAYER = "Unknown player"

# Legend words.
CORP = "Corp"
RUNNER = "Runner"
STANDINGS_LEGEND = f"{CORP} + SoS on line 2, {RUNNER} on line 3"


def _count(count: int, noun: str) -> str:
    return f"{count} {noun}" if count == 1 else f"{count} {noun}s"


# Embed footers: a legend for the table (footers cannot show timestamps).


def standings_footer(after_round: int | None, players: int) -> str:
    parts = [f"Round {after_round}"] if after_round else []
    parts += [_count(players, "player"), STANDINGS_LEGEND]
    return " · ".join(parts)


def pairings_footer(round_number: int, tables: int, double_sided: bool) -> str:
    legend = (
        "double-sided · columns = game 1 | game 2"
        if double_sided
        else f"{CORP} first · number = points scored"
    )
    return f"Round {round_number} · {_count(tables, 'table')} · {legend}"


PLAYERS_FOOTER = f"{STANDINGS_LEGEND} · pairing: {CORP} first · number = points scored"


def tournament_fallback_name(tournament_id: int) -> str:
    return f"Tournament {tournament_id}"


# --- reply images (formatting.image) --------------------------------------------

# Column headings.
RANK = "#"
PLAYER = "Player"
TABLE = "Table"
SIDE = "Side"
IDENTITY = "ID"
POINTS = "Pts"
SOS = "SoS"
TOTAL = "Total"
GAME = "Game"
RESULT = "W/L"
SEED = "Seed"
RECORD = "W–L"
OPPONENT = "Opponent"
SCORE = "Score"
NOT_PAIRED = "not paired"


def game_heading(game: int) -> str:
    return f"Game {game}"


def page_indicator(page: int, pages: int) -> str:
    return f"{page} / {pages}"


# Legends below an image: the columns have headings, so no key is needed.


def compact_standings_footer(after_round: int | None, players: int) -> str:
    parts = [f"Round {after_round}"] if after_round else []
    return " · ".join([*parts, _count(players, "player")])


def compact_pairings_footer(round_number: int, tables: int) -> str:
    return f"Round {round_number} · {_count(tables, 'table')}"


def compact_cut_pairings_footer(round_number: int, games: int) -> str:
    return f"Round {round_number} · {_count(games, 'game')}"


def compact_top_cut_footer(size: int, players: int) -> str:
    return f"Top {size} · {_count(players, 'player')} · W–L = games won and lost"


def compact_bracket_footer(games: int) -> str:
    return f"{_count(games, 'game')} · bold = winner"


def record(wins: int, losses: int) -> str:
    return f"{wins}–{losses}"


# Bracket slots whose player is not known yet.
UPPER_BRACKET = "Upper bracket"
LOWER_BRACKET = "Lower bracket"
TBD = "TBD"


def seed_slot(seed: int) -> str:
    return f"Seed {seed}"


def winner_of(game: int) -> str:
    return f"Winner of {game}"


def loser_of(game: int) -> str:
    return f"Loser of {game}"


def compact_players_footer(round_number: int | None, players: int) -> str:
    parts = [f"Round {round_number}"] if round_number else []
    return " · ".join([*parts, _count(players, "player")])


# --- command registration (SPEC §2) --------------------------------------------

COMMAND_DESCRIPTION = "Pairings and standings from Cobra tournaments"
PAIRINGS_DESCRIPTION = "Show pairings for a round, Swiss or top cut"
STANDINGS_DESCRIPTION = "Show the Swiss standings"
TOP_CUT_DESCRIPTION = "Show the top-cut ranking"
BRACKET_DESCRIPTION = "Show the top-cut bracket"
PLAYER_DESCRIPTION = "Find players and their latest pairing"
TOURNAMENT_OPTION_DESCRIPTION = "Cobra tournament ID, link or shortcode"
ROUND_OPTION_DESCRIPTION = "Round number, Swiss or top cut (default: the latest)"
QUERY_OPTION_DESCRIPTION = "Part of a player's name; several, separated by commas"
