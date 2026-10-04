# Tests

- Mirror `src/`: a module's tests go in the matching file (`formatting/header.py` → `tests/formatting/test_header.py`). Test at the lowest layer that holds the logic; `test_commands.py` covers commands end to end with fakes, `handlers/test_worker.py` only the wiring.
- Build inputs with `tests/builders.py` (`player`, `seat`, `pairing`, `tournament`, `FETCHED_AT`) instead of loading a fixture when a few players suffice. Fixtures (`docs/spec/fixtures.md`) through the `raw_fixture` fixture in `conftest.py`; refer to players by fixture ID, never by name.
- No network, no AWS: mocked HTTP (`httpx.MockTransport`), `InMemoryCacheStore`, botocore `Stubber`, fake clocks.
- Mark what a test covers: `@pytest.mark.req("FR-09", "AC-27")`, or a module-level `pytestmark`. `test_traceability.py` fails when an `Implemented`/`Partly` requirement or an automated AC has no marked test, an exempt one has a test, or a marker names an unknown ID.
- Drawing is slow: share `cobra_bot.fonts.load()` at module scope, and check tables (`standings_table`, …) rather than PNG pixels unless the drawing itself is under test.
- Run one file: `uv run pytest tests/formatting/test_header.py -q`.
