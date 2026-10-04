from typing import Any

from cobra_bot.registration import command_definition


def _options(definition: dict[str, Any]) -> dict[str, dict[str, Any]]:
    # Any: the definition is a JSON-shaped dict.
    return {o["name"]: o for o in definition["options"]}


def test_ac24_integration_types_and_contexts() -> None:
    definition = command_definition()

    assert definition["integration_types"] == [0, 1]
    assert definition["contexts"] == [0, 1, 2]


def test_command_shape_matches_spec_section_2() -> None:
    definition: dict[str, Any] = command_definition()
    subcommands = _options(definition)

    assert (definition["name"], definition["type"]) == ("cobra", 1)
    assert list(subcommands) == [
        "pairings",
        "standings",
        "top-cut",
        "bracket",
        "player",
    ]
    assert all(s["type"] == 1 for s in subcommands.values())

    pairings = _options(subcommands["pairings"])
    assert pairings["tournament"] == {
        **pairings["tournament"],
        "type": 3,
        "required": True,
    }
    assert pairings["round"] == {
        **pairings["round"],
        "type": 4,
        "required": False,
        "min_value": 1,
    }

    assert list(_options(subcommands["standings"])) == ["tournament"]
    assert list(_options(subcommands["top-cut"])) == ["tournament"]
    assert list(_options(subcommands["bracket"])) == ["tournament"]

    player = _options(subcommands["player"])
    assert player["query"] == {
        **player["query"],
        "type": 3,
        "required": True,
        "min_length": 1,
        "max_length": 200,
    }


def test_descriptions_fit_discord_limits() -> None:
    definition: dict[str, Any] = command_definition()
    descriptions = [definition["description"]]
    for sub in definition["options"]:
        descriptions.append(sub["description"])
        descriptions += [o["description"] for o in sub["options"]]

    assert all(1 <= len(d) <= 100 for d in descriptions)
