# Requirements — Cobra Discord Bot

Status: Draft v0.4 · 2026-10-04

## 1. Purpose

Netrunner players, organisers and spectators coordinate tournaments on many different Discord servers. Checking pairings and standings means leaving Discord for Cobra (https://tournaments.nullsignal.games/), and during large events many simultaneous visits can make Cobra slow or unresponsive.

The bot lets anyone read pairings and standings of a Cobra tournament directly in Discord, and reduces load on Cobra by serving tournament data from a shared cache.

## 2. Users

- **Tournament organisers (TOs)** — install the bot and share pairings/standings with players.
- **Players** — check their pairing and position.
- **Spectators / community** — follow the tournament.

The bot is public. It can be added to any Discord server (server install) and by any user to their own account (user install).

## 3. Priority legend

- **Must** — required for MVP.
- **Should** — desirable in MVP if cheap; otherwise first follow-up.
- **Could** — later, after MVP.
- **Out of scope** — not planned for this specification.

## 4. Functional requirements

**Status** says whether the requirement is in the code (as of 2026-10-04). **Tests** names the tests that cover it, as `file` (under `tests/`) and test function; acceptance criteria (`AC-xx`, SPEC §13) carry their ID in the test name. Keep both columns up to date when a requirement or its tests change.

| ID | Priority | Requirement | Status | Tests |
|----|----------|-------------|--------|-------|
| FR-01 | Must | Slash command `/cobra pairings <tournament> [round]` posts pairings publicly in the channel. | Implemented | `test_commands.py` `test_pairings`<br>`handlers/test_worker.py` `test_pairings_end_to_end`<br>`handlers/test_interactions.py` `test_public_commands_are_deferred_without_flags` |
| FR-02 | Must | Without `round`, pairings are shown for the latest round, Swiss or top cut (changed 2026-10-04: the latest round always). With `round`, for that round; rounds are numbered by their position in Cobra's export, Swiss rounds first, then the top-cut rounds. A top-cut round is headed "Top cut round N pairings" and shows game numbers and the winner (`W`/`L`) instead of tables and points. | Implemented | `domain/test_rounds.py` `test_ac03_default_pairings_show_the_latest_round_even_in_the_top_cut`<br>`domain/test_rounds.py` `test_ac04_a_requested_elimination_round_is_its_bracket_round`<br>`domain/test_rounds.py` `test_requested_swiss_round`<br>`formatting/test_pairings.py` `test_top_cut_game_shows_its_number_and_winner`<br>`test_commands.py` `test_pairings_of_a_top_cut_round` |
| FR-03 | Must | Pairings output states which round it shows and whether that round is in progress or complete. | Implemented | `domain/test_rounds.py` `test_ac07_round_in_progress`<br>`formatting/test_pairings.py` `test_ac07_in_progress_header` |
| FR-04 | Must | Each pairing shows: table number, both player names, roles and identities (IDs), and results if reported. Byes and intentional draws are shown explicitly. | Implemented | `formatting/test_pairings.py` `test_single_sided_layout_and_colours`<br>`formatting/test_pairings.py` `test_bye`<br>`formatting/test_pairings.py` `test_intentional_draw_shows_id_and_plain_names`<br>`formatting/test_image.py` `test_single_sided_corp_first_winner_bold_loser_secondary`<br>`formatting/test_image.py` `test_ac02_bye_at_table_21` |
| FR-05 | Must | Both single-sided Swiss (one game per round) and double-sided Swiss (two games per round) are supported. | Implemented | `domain/test_rounds.py` `test_ac22_double_sided_pairing_needs_both_games`<br>`formatting/test_pairings.py` `test_ac22_double_sided_pairing_shows_both_games`<br>`formatting/test_image.py` `test_ac22_double_sided_shows_both_games` |
| FR-06 | Must | Slash command `/cobra standings <tournament>` posts the Swiss standings publicly, stating after which round they apply. If no round is complete yet, it says "No completed rounds yet" and lists the players in the order Cobra gives them (`rank`). Once Swiss is over (every Swiss round so far complete and counted, or a cut made), a note gives the top cut's state: none on Cobra yet, announced but not started, in progress, or finished (FR-22). | Implemented | `formatting/test_standings.py` `test_ac01_finished_tournament`<br>`formatting/test_standings.py` `test_ac08_no_completed_round_lists_players_in_rank_order`<br>`domain/test_rounds.py` `test_ac07_complete_round_not_yet_counted_by_cobra`<br>`formatting/test_standings.py` `test_cut_note_sits_between_the_title_and_the_data_line` |
| FR-07 | Must | Each standings row shows: rank, player name, match points, Strength of Schedule (SoS), Corp ID and Runner ID. | Implemented | `formatting/test_image.py` `test_standings_columns_ids_before_points_and_sos`<br>`formatting/test_image.py` `test_standings_row_values_and_colours`<br>`formatting/test_image.py` `test_ac01_standings_first_row` |
| FR-08 | Must | IDs are displayed in short form: the text before the first `:`, mapped to a short name of at most 9 columns (e.g. "Nuvem SA: Law of the Land" → "Nuvem"). Where several IDs share that text (Haas-Bioroid, Jinteki, NBN, Weyland Consortium), each ID has its own short name: the faction and the ID's initials (e.g. "Haas-Bioroid: Precision Design" → "HB PD", "NBN: Reality Plus" → "NBN R+"; changed 2026-10-04). There is a fallback for IDs missing from the map (SPEC §9; `docs/embeded_format.md` A-1–A-4). The images use the same short names. | Implemented | `formatting/test_text.py` `test_corp_label`<br>`formatting/test_text.py` `test_runner_label`<br>`formatting/test_text.py` `test_missing_id_is_logged_once`<br>`formatting/test_image.py` `test_ids_are_always_the_short_name`<br>`scripts/test_generate_identities.py` `test_ids_sharing_a_key_get_full_title_entries_and_keep_the_key` |
| FR-09 | Must | Slash command `/cobra player <tournament> <query>` replies publicly (changed from ephemeral on 2026-10-03, so a group can follow its players together). `query` may list up to 10 names separated by commas, e.g. `Alice, Bob, Carol`; each is searched on its own and every matching player gets a card, once, in rank order. Matching is a substring match that ignores letter case and diacritics (e.g. `maelig` matches "Maëlig", `zolw` matches "Żółw"). | Implemented | `domain/test_search.py` `test_ac09_substring_in_different_case_finds_one_player`<br>`domain/test_search.py` `test_ac12_diacritics_are_ignored`<br>`domain/test_search.py` `test_several_names_union_in_rank_order_once_each`<br>`handlers/test_interactions.py` `test_ac19_player_is_deferred_publicly_and_worker_invoked_async` |
| FR-10 | Must | Player search returns up to 3 matches, ordered by rank; if more exist, it says how many more matched. Each match shows rank, points, SoS, IDs and the player's pairing in the latest round, Swiss or top cut (table or game, opponent, role, result) or bye. | Implemented | `domain/test_search.py` `test_ac10_more_than_three_matches`<br>`domain/test_search.py` `test_matches_are_ordered_by_rank_and_limited`<br>`formatting/test_image.py` `test_players_table_columns_after_a_round`<br>`formatting/test_image.py` `test_player_row_in_a_cut_game_shows_w_or_l` |
| FR-11 | Must | `<tournament>` accepts a numeric ID or a Cobra URL (any page under `/tournaments/{id}/…`). | Implemented | `cobra/test_refs.py` `test_ac13_valid_references`<br>`cobra/test_refs.py` `test_ac13_invalid_references` |
| FR-12 | Should | `<tournament>` also accepts a shortcode (e.g. `HBYM`), if Cobra offers a reliable way to resolve it (see T01). | Implemented | `cobra/test_client.py` `test_shortcode_resolves_from_redirect`<br>`cobra/test_cache.py` `test_shortcode_is_resolved_and_remembered`<br>`test_commands.py` `test_shortcode_reference` |
| FR-13 | Must | If the tournament has not started (no rounds), the bot says so; standings instead list the registered players, if there are any, as Cobra does (SPEC AC-26). | Implemented | `domain/test_rounds.py` `test_ac06_no_rounds_means_not_started`<br>`domain/test_rounds.py` `test_ac26_registered_players_listed_by_name_like_cobra`<br>`test_commands.py` `test_ac26_standings_before_the_first_round_list_the_registered_players` |
| FR-14 | Must | Output uses Discord embeds; standings, pairings and player search show their table as an image in the embed (decided 2026-10-03, SPEC §9). Long output is split across up to 5 messages (images: up to 5 pages, all in one message); if it does not fit, the last message (page) says how many entries were omitted and links to the full page on Cobra. | Implemented | `formatting/test_image.py` `test_at_most_five_messages_and_the_rest_counted`<br>`formatting/test_image.py` `test_large_tournament_fits_the_limits`<br>`formatting/test_chunking.py` `test_ac15_thousand_players_are_cut_with_a_link`<br>`discord/test_api.py` `test_image_pages_go_in_one_message_in_place_of_the_deferral` |
| FR-15 | Must | If Cobra is unavailable, the bot shows the last cached data with a note stating when it was fetched. If no cached data exists, it shows an error. | Implemented | `cobra/test_cache.py` `test_ac17_failing_fetch_serves_old_entry_marked_stale`<br>`cobra/test_cache.py` `test_ac17_failing_fetch_without_cache_raises_unavailable`<br>`test_commands.py` `test_stale_data_is_served_with_notice` |
| FR-16 | Must | Clear user-facing errors for: invalid tournament reference, tournament not found, tournament private (without cache), round out of range, Cobra unavailable without cache. | Implemented | `test_commands.py` `test_invalid_reference`<br>`test_commands.py` `test_not_found`<br>`test_commands.py` `test_round_state_errors`<br>`test_commands.py` `test_cobra_failures_without_cache` |
| FR-17 | Must | All bot responses are in English. | Implemented | No automated test; all user-facing text is in `messages.py` |
| FR-18 | Must | Commands work in servers where the bot is installed, and — for users who installed the bot on their account — in any server, DM or group DM. | Implemented | `test_registration.py` `test_ac24_integration_types_and_contexts`<br>Manual: `docs/acceptance.md` B1–B4 |
| FR-19 | Must | Top cut (elimination) pairings (FR-02), bracket (FR-24) and ranking (FR-23). Added 2026-10-04, replacing the MVP reply "Top cut is not supported yet". | Implemented | See FR-02, FR-23, FR-24 |
| FR-20 | Could | Extended SoS (eSoS) column in standings. | Not implemented | — |
| FR-22 | Must | The top cut's state is derived from Cobra's export: none (`cutToTop` 0, no elimination round), announced (`cutToTop` set, no elimination round), in progress (an elimination round), finished (Cobra has placed a player first in `eliminationPlayers`). | Implemented | `domain/test_bracket.py` `test_status_none_without_a_cut`<br>`domain/test_bracket.py` `test_status_announced_once_the_cut_is_made`<br>`domain/test_bracket.py` `test_status_in_progress_with_a_cut_round`<br>`domain/test_bracket.py` `test_status_finished_once_cobra_places_the_winner`<br>`domain/test_rounds.py` `test_cut_note_in_progress_and_finished` |
| FR-23 | Must | Slash command `/cobra top-cut <tournament>` posts the top-cut ranking publicly, like standings: place (blank while Cobra has not decided it), player, Corp and Runner ID, games won and lost in the cut, seed. Players still in the cut come first, by seed, then those out but not placed, the later out higher; players out are shown secondary. Without a cut: "This tournament has no top cut on Cobra yet." | Implemented | `domain/test_bracket.py` `test_placed_players_take_their_places_and_the_rest_wait_above_them`<br>`domain/test_bracket.py` `test_still_playing_before_out_and_later_out_higher`<br>`formatting/test_image.py` `test_top_cut_rows_still_in_bold_out_secondary_undecided_rank_blank`<br>`test_commands.py` `test_top_cut`<br>`test_commands.py` `test_no_top_cut` |
| FR-24 | Must | Slash command `/cobra bracket <tournament>` posts the top-cut bracket publicly as an image laid out like Cobra's bracket page (`/tournaments/{id}/bracket`): a column per bracket round, upper bracket above lower, a box per game with its number, links to the game its winner plays next; without faction logos or pronouns, IDs as short names. Unknown players say where they come from (`Seed 3`, `Winner of 13`, `Loser of 21`). Cobra's brackets (double elimination top 4/8/16, single elimination top 2/3/4/8/16) are supported; another cut size replies "There is no bracket for a top N cut." | Implemented | `domain/test_bracket.py` `test_real_cuts_fit_the_double_elimination_template`<br>`domain/test_bracket.py` `test_top8_single_elimination_is_told_by_round_one_seeds`<br>`formatting/test_bracket_image.py` (layout, slots, drawing)<br>`test_commands.py` `test_bracket`<br>`test_commands.py` `test_bracket_for_a_cut_size_without_one` |
| FR-21 | Must | Organisers can switch a tournament between public and private while it runs. If Cobra reports the tournament as private and cached data exists, the bot shows the cached data with a note that the tournament is now private and when the data was fetched. Without cached data, it says the tournament is private. | Implemented | `cobra/test_cache.py` `test_ac25_private_tournament_serves_cache_marked_private_and_keeps_entry`<br>`cobra/test_cache.py` `test_ac25_private_tournament_without_cache_raises_private`<br>`cobra/test_client.py` `test_401_is_private` |

## 5. Non-functional requirements

| ID | Priority | Requirement | Status | Tests |
|----|----------|-------------|--------|-------|
| NFR-01 | Must | Anyone who can use application commands can use all bot commands; no role restrictions. | Implemented | No automated test; the registration sets no `default_member_permissions` |
| NFR-02 | Must | Tournament data is cached in a shared cache (Amazon S3) for at most 60 seconds; all bot instances use the same cache. | Implemented | `cobra/test_cache.py` `test_ac16_second_request_within_ttl_uses_cache_and_after_ttl_refetches`<br>`test_template.py` `test_worker_may_only_use_its_bucket` |
| NFR-03 | Should | Concurrent cache misses for the same tournament result in a single fetch from Cobra (single-flight). | Implemented | `cobra/test_cache.py` `test_ac18_waiting_caller_gets_fresh_object_without_http`<br>`cobra/test_cache.py` `test_abandoned_lock_is_taken_over`<br>`cobra/test_s3_store.py` `test_lock_is_created_with_if_none_match` |
| NFR-04 | Must | Every interaction is acknowledged within Discord's 3-second limit. | Implemented | `handlers/test_interactions.py` `test_ac19_player_is_deferred_publicly_and_worker_invoked_async`<br>`handlers/test_import_cost.py` `test_interactions_handler_does_not_load_pillow`<br>`test_template.py` `test_interactions_function_has_cpu_for_a_cold_start` |
| NFR-05 | Should | Final response delivered within TBD seconds (p95, warm instance). | Not testable yet | Target is TBD |
| NFR-06 | Must | A command never produces duplicate messages (no automatic retries of partially completed work). | Implemented | `test_template.py` `test_ac23_worker_is_never_retried`<br>`test_template.py` `test_worker_events_expire_with_the_interaction_token` |
| NFR-07 | Must | Discord request signatures (Ed25519) are verified; invalid requests are rejected with HTTP 401. | Implemented | `discord/test_verify.py`<br>`handlers/test_interactions.py` `test_ac19_invalid_signature_is_401`<br>`handlers/test_interactions.py` `test_ac19_missing_signature_is_401` |
| NFR-08 | Must | The bot token is used only by the local command registration script, from environment variables; it is never stored in AWS, the repository or logs. Deployed configuration (Discord public key, resource names) comes from template parameters as environment variables; nothing account- or bot-specific is hard-coded, so several bots or AWS accounts can run the same code. | Implemented | `scripts/test_register_commands.py` `test_http_error_fails_without_printing_the_token`<br>`test_template.py` `test_environment_variables_match_the_code`<br>`test_template.py` `test_no_function_reads_ssm` |
| NFR-09 | Must | No persistent storage of user data. Only a cache of public tournament data, expiring automatically. | Implemented | `test_template.py` `test_ac23_cache_bucket_expires_objects`<br>`handlers/test_interactions.py` `test_worker_payload_carries_no_user_data` |
| NFR-10 | Must | Bot messages never trigger mentions (`allowed_mentions` empty); player names cannot inject markup: they are shown inside code blocks they cannot close, and user text outside code blocks is escaped for Discord markdown. | Implemented | `discord/test_api.py` `test_ac21_every_payload_blocks_mentions_and_names_stay_in_code_blocks`<br>`formatting/test_pairings.py` `test_names_are_literal_and_cannot_close_the_code_block`<br>`formatting/test_players.py` `test_query_is_escaped` |
| NFR-11 | Must | Test fixtures derived from real tournaments are anonymised before being committed. | Implemented | `test_fixtures.py` `test_fixture_is_anonymised`<br>`scripts/test_anonymize_fixture.py` `test_no_original_personal_data_remains` |
| NFR-12 | Must | Logs go to CloudWatch with 14-day retention; full Cobra payloads are not logged. | Partly | `test_template.py` `test_logs_are_kept_14_days`<br>`test_template.py` `test_functions_log_to_their_groups`<br>No test that Cobra payloads stay out of the logs |
| NFR-13 | Must | AWS budget alarm at USD 5/month. | Implemented | `test_template.py` `test_budget_is_5_usd_per_month`<br>`test_template.py` `test_budget_alerts_go_to_the_email_parameter` |
| NFR-14 | Must | Infrastructure defined with AWS SAM in region `eu-central-1`; deployed by GitHub Actions when `main` moves (`.github/workflows/deploy.yml`), or manually with `sam deploy`. | Implemented | `test_template.py`<br>`test_deploy_setup.py` `test_deploy_runs_after_ci_on_main`<br>`test_deploy_setup.py` `test_workflow_deploys_to_the_configured_region` |
| NFR-15 | Must | GitHub Actions runs lint, type-check and tests on every push and pull request. | Implemented | No automated test; `.github/workflows/ci.yml` |
| NFR-16 | Must | Requests to Cobra use an identifying User-Agent, an 8-second timeout, and no aggressive retries. | Implemented | `cobra/test_client.py` `test_http_client_settings`<br>`cobra/test_client.py` `test_timeout_is_unavailable` |
| NFR-17 | Should | Running cost stays within the AWS free tier at expected load (load TBD). | Not testable yet | Load is TBD; budget alert: NFR-13 |
| NFR-18 | Could | Logs archived to S3. | Not implemented | — |

## 6. Constraints

- Language: Python 3.14, the latest version supported by the AWS Lambda managed runtime.
- Hosting: AWS Lambda with Discord HTTP interactions (no Gateway connection); Discord scope `applications.commands` only.
- Developed by one person with AI assistance; no deadline.
- Data source: Cobra public JSON export (`/tournaments/{id}.json`). Not an official API; no agreement with Null Signal Games (NSG) yet.

## 7. Out of scope (MVP)

- Automatic publishing of new pairings/standings to a channel (would need the `bot` scope).
- Linking a channel to a tournament (`/cobra track`) and any persistent state beyond the cache.
- Notifications to individual players; mapping Cobra players to Discord users.
- Public HTTP API for other bots.
- Text/prefix commands (e.g. `!pairings`) and a Gateway (WebSocket) connection.

## 8. Open items (TBD)

- Response-time target, expected load.
- NSG consent — to be requested after showing the MVP.
