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


def player_round(round_number: int, pairing: str) -> str:
    """A player's pairing (already formatted) in the given round."""
    return f"Round {round_number}: {pairing}"


def more_players_matched(count: int) -> str:
    return f"…and {count} more matched"


def omitted_entries(count: int, url: str) -> str:
    return f"…and {count} more — [full list on Cobra]({url})"


# --- entry vocabulary -----------------------------------------------------------

CORP = "Corp"
RUNNER = "Runner"
BYE = "BYE"
INTENTIONAL_DRAW = "ID"
VERSUS = "vs"
UNKNOWN_IDENTITY = "?"
UNKNOWN_PLAYER = "Unknown player"
NOT_PAIRED = "not paired"
POINTS = "pts"
SOS = "SoS"


def tournament_fallback_name(tournament_id: int) -> str:
    return f"Tournament {tournament_id}"
