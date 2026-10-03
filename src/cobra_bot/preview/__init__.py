"""Reply layouts under test, shown only by `scripts/preview.py`.

The bot does not import this package: its replies stay in format A (embeds,
`cobra_bot.formatting`). `tests/preview/test_isolation.py` checks that.

- B2 (`components`): Components V2 in plain markdown, the same on desktop and
  mobile, with page buttons, a refresh button and a round select.
- C (`image`): the table as a PNG image in an embed.
"""
