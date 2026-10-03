"""Reply layouts under test, shown only by `scripts/preview.py`.

The bot does not import this package: its replies stay in format A (embeds,
`cobra_bot.formatting`). `tests/preview/test_isolation.py` checks that.

- B1 (`components`): format A's ```ansi table in a Components V2 container with
  page buttons, a refresh button and a round select.
- B2 (`components`): Components V2 with plain markdown for narrow screens.
- C (`image`): the table as a PNG image in an embed.
"""
