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
TOP_CUT_NOT_SUPPORTED = "Top cut is not supported yet."
NO_PLAYERS_MATCH = "No players match."
UNKNOWN_COMMAND = "Unknown command."
INTERNAL_ERROR = "Something went wrong. Please try again later."
COBRA_DATA_UNREADABLE = "Cobra returned data the bot cannot read."


def round_out_of_range(requested: int, last_round: int) -> str:
    return (
        f"Round {requested} does not exist. This tournament has rounds 1–{last_round}."
    )


# --- headers and notes (SPEC §9) -------------------------------------------------

TOP_CUT_IN_PROGRESS = "Top cut in progress — not supported yet"
NO_COMPLETED_ROUNDS = "No completed rounds yet"
IN_PROGRESS = "in progress"
COMPLETE = "complete"


def pairings_header(round_number: int, complete: bool) -> str:
    state = COMPLETE if complete else IN_PROGRESS
    return f"Round {round_number} pairings — {state}"


def standings_header(after_round: int) -> str:
    return f"Standings after round {after_round}"


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


def omitted_entries(count: int, url: str) -> str:
    return f"…and {count} more — [full list on Cobra]({url})"


# --- entry vocabulary -----------------------------------------------------------

BYE = "BYE"
INTENTIONAL_DRAW = "ID"
VERSUS = "vs"
UNKNOWN_IDENTITY = "—"
UNKNOWN_PLAYER = "Unknown player"

# Table column headings.
RANK = "#"
PLAYER = "Player"
POINTS = "Pts"
SOS = "SoS"
CORP = "Corp"
RUNNER = "Runner"
TABLE = "T"
SCORE = "Score"


def _count(count: int, noun: str) -> str:
    return f"{count} {noun}" if count == 1 else f"{count} {noun}s"


# Embed footers: a legend for the table (footers cannot show timestamps).


def standings_footer(after_round: int | None, players: int) -> str:
    parts = [f"Round {after_round}"] if after_round else []
    parts += [_count(players, "player"), f"{POINTS} / {SOS} / {CORP} / {RUNNER}"]
    return " · ".join(parts)


def pairings_footer(round_number: int, tables: int) -> str:
    return (
        f"Round {round_number} · {_count(tables, 'table')} · "
        f"{CORP} left, {RUNNER} right · score from {CORP} side"
    )


PLAYERS_FOOTER = (
    f"{POINTS} / {SOS} / {CORP} / {RUNNER} · pairing: {CORP} left, {RUNNER} right"
)


def tournament_fallback_name(tournament_id: int) -> str:
    return f"Tournament {tournament_id}"


# --- command registration (SPEC §2) --------------------------------------------

COMMAND_DESCRIPTION = "Pairings and standings from Cobra tournaments"
PAIRINGS_DESCRIPTION = "Show pairings for a Swiss round"
STANDINGS_DESCRIPTION = "Show the current standings"
PLAYER_DESCRIPTION = "Find players and their latest pairing (only you see it)"
TOURNAMENT_OPTION_DESCRIPTION = "Cobra tournament ID, link or shortcode"
ROUND_OPTION_DESCRIPTION = "Swiss round number (default: the latest)"
QUERY_OPTION_DESCRIPTION = "Part of the player's name"
