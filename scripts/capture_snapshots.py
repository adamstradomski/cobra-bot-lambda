#!/usr/bin/env python3
# /// script
# requires-python = ">=3.14"
# dependencies = []
# ///
"""Capture raw Cobra tournament JSON snapshots for discovery (task T01).

Poll mode fetches ``/tournaments/{id}.json`` at a fixed interval and stores each
changed response under ``snapshots/{id}/``. Probe mode fetches arbitrary paths
once, without following redirects, to record status codes and redirect targets
(shortcodes, non-existent and unpublished tournaments).

Standard library only. See README.md for usage and exit codes.
"""

import argparse
import gzip
import hashlib
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import UTC, datetime
from email.message import Message
from pathlib import Path
from typing import Any

DEFAULT_BASE_URL = "https://tournaments.nullsignal.games"
USER_AGENT = "cobra-bot-lambda-snapshots/0.1 (+https://github.com/adamstradomski/cobra-bot-lambda)"
TIMEOUT_S = 8.0
MIN_INTERVAL_S = 60.0
DEFAULT_INTERVAL_S = 120.0
PROBE_BODY_PREVIEW_CHARS = 500
KEPT_HEADERS = (
    "Content-Type",
    "Content-Length",
    "Content-Encoding",
    "ETag",
    "Last-Modified",
    "Cache-Control",
    "Location",
)

EXIT_OK = 0
EXIT_FETCH_FAILED = 1
EXIT_USAGE = 2


@dataclass(frozen=True)
class Response:
    url: str
    final_url: str
    status: int
    headers: dict[str, str]
    body: bytes
    duration_s: float


class FetchError(Exception):
    """Network-level failure: timeout, DNS, connection refused, TLS error."""


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(
        self, *args: Any, **kwargs: Any
    ) -> None:  # Any: mirrors base signature
        return None


def _kept_headers(message: Message) -> dict[str, str]:
    return {name: message[name] for name in KEPT_HEADERS if message[name] is not None}


def _decode_body(raw: bytes, headers: dict[str, str]) -> bytes:
    if headers.get("Content-Encoding", "").lower() == "gzip":
        return gzip.decompress(raw)
    return raw


def fetch(url: str, *, follow_redirects: bool) -> Response:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/json, */*;q=0.5",
            "Accept-Encoding": "gzip",
        },
    )
    handlers = [] if follow_redirects else [_NoRedirect()]
    opener = urllib.request.build_opener(*handlers)
    started = time.monotonic()
    try:
        with opener.open(request, timeout=TIMEOUT_S) as resp:
            headers = _kept_headers(resp.headers)
            raw = resp.read()
            status = resp.status
            final_url = resp.geturl()
    except urllib.error.HTTPError as err:
        # Non-2xx (and 3xx when redirects are disabled) still carry a useful response.
        headers = _kept_headers(err.headers)
        raw = err.read()
        status = err.code
        final_url = url
    except (urllib.error.URLError, TimeoutError, OSError) as err:
        raise FetchError(f"{type(err).__name__}: {err}") from err
    duration = time.monotonic() - started
    try:
        body = _decode_body(raw, headers)
    except (OSError, EOFError) as err:
        raise FetchError(f"invalid gzip body: {err}") from err
    return Response(url, final_url, status, headers, body, duration)


def summarize(data: object) -> dict[str, object] | None:
    """Summarise a tournament export's structure; None if the shape is unrecognised."""
    if not isinstance(data, dict):
        return None
    players = data.get("players")
    rounds = data.get("rounds")
    summary: dict[str, object] = {
        "name_present": "name" in data,
        "players": len(players) if isinstance(players, list) else None,
        "rounds": len(rounds) if isinstance(rounds, list) else None,
    }
    if isinstance(rounds, list):
        per_round: list[dict[str, int]] = []
        for rnd in rounds:
            pairings = rnd if isinstance(rnd, list) else []
            per_round.append(
                {
                    "pairings": len(pairings),
                    "elimination": sum(
                        1
                        for p in pairings
                        if isinstance(p, dict) and p.get("eliminationGame")
                    ),
                }
            )
        summary["per_round"] = per_round
    return summary


def utc_stamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def unique_stem(directory: Path, stem: str) -> str:
    candidate, n = stem, 1
    while any(directory.glob(f"{candidate}.*")):
        candidate, n = f"{stem}-{n}", n + 1
    return candidate


def write_atomic(path: Path, data: bytes) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)


def write_json(path: Path, obj: object) -> None:
    write_atomic(path, (json.dumps(obj, indent=2, ensure_ascii=False) + "\n").encode())


def response_meta(resp: Response) -> dict[str, object]:
    return {
        "url": resp.url,
        "final_url": resp.final_url,
        "status": resp.status,
        "headers": resp.headers,
        "duration_s": round(resp.duration_s, 3),
        "body_bytes": len(resp.body),
        "body_sha256": hashlib.sha256(resp.body).hexdigest(),
    }


def log(message: str) -> None:
    print(f"{datetime.now(UTC):%H:%M:%SZ} {message}", file=sys.stderr, flush=True)


# --- poll mode ---------------------------------------------------------------


def latest_snapshot_hash(directory: Path) -> str | None:
    snapshots = sorted(
        p for p in directory.glob("*.json") if not p.name.endswith(".meta.json")
    )
    if not snapshots:
        return None
    return hashlib.sha256(snapshots[-1].read_bytes()).hexdigest()


def capture_once(
    tournament_id: int, base_url: str, out: Path, last_hash: dict[int, str]
) -> bool:
    """Fetch one export and store it if changed. True on HTTP 200 with valid JSON."""
    directory = out / str(tournament_id)
    directory.mkdir(parents=True, exist_ok=True)
    if tournament_id not in last_hash:
        previous = latest_snapshot_hash(directory)
        if previous is not None:
            last_hash[tournament_id] = previous

    url = f"{base_url}/tournaments/{tournament_id}.json"
    fetched_at = datetime.now(UTC)
    try:
        resp = fetch(url, follow_redirects=True)
    except FetchError as err:
        log(f"{tournament_id}: fetch failed ({err})")
        return False

    meta = {"fetched_at": fetched_at.isoformat(), **response_meta(resp)}
    stem = unique_stem(directory, fetched_at.strftime("%Y%m%dT%H%M%SZ"))
    size = f"{len(resp.body)} B in {resp.duration_s:.2f}s"

    data: object = None
    valid_json = False
    if resp.status == 200:
        try:
            data = json.loads(resp.body)
            valid_json = True
        except ValueError:
            pass

    if not valid_json:
        meta["error"] = "non-200 status" if resp.status != 200 else "invalid JSON"
        write_atomic(directory / f"{stem}.body.txt", resp.body)
        write_json(directory / f"{stem}.meta.json", meta)
        log(
            f"{tournament_id}: HTTP {resp.status}, {meta['error']}, {size}"
            f" -> {stem}.body.txt"
        )
        return False

    digest = str(meta["body_sha256"])
    if last_hash.get(tournament_id) == digest:
        log(f"{tournament_id}: HTTP 200, {size}, unchanged")
        return True

    meta["summary"] = summarize(data)
    write_atomic(directory / f"{stem}.json", resp.body)
    write_json(directory / f"{stem}.meta.json", meta)
    last_hash[tournament_id] = digest
    log(f"{tournament_id}: HTTP 200, {size}, saved {stem}.json")
    return True


def run_poll(
    ids: list[int], base_url: str, out: Path, interval: float, count: int | None
) -> int:
    last_hash: dict[int, str] = {}
    cycle = 0
    next_start = time.monotonic()
    while True:
        cycle += 1
        results = [capture_once(tid, base_url, out, last_hash) for tid in ids]
        if count is not None and cycle >= count:
            if count == 1 and not all(results):
                return EXIT_FETCH_FAILED
            return EXIT_OK
        next_start += interval
        time.sleep(max(0.0, next_start - time.monotonic()))


# --- probe mode --------------------------------------------------------------


def slugify(path: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", path.strip("/")) or "root"


def body_extension(resp: Response) -> str:
    return ".json" if "json" in resp.headers.get("Content-Type", "").lower() else ".txt"


def probe_record(resp: Response) -> dict[str, object]:
    record = response_meta(resp)
    record["body_preview"] = resp.body[:PROBE_BODY_PREVIEW_CHARS].decode(
        "utf-8", "replace"
    )
    return record


def probe_one(path: str, base_url: str, out: Path) -> bool:
    directory = out / "probes"
    directory.mkdir(parents=True, exist_ok=True)
    stem = unique_stem(directory, f"{utc_stamp()}_{slugify(path)}")
    url = base_url + path
    meta: dict[str, object] = {"probed_at": datetime.now(UTC).isoformat(), "path": path}

    try:
        resp = fetch(url, follow_redirects=False)
    except FetchError as err:
        meta["error"] = str(err)
        write_json(directory / f"{stem}.meta.json", meta)
        log(f"probe {path}: fetch failed ({err})")
        return False

    meta["response"] = probe_record(resp)
    if resp.body:
        write_atomic(directory / f"{stem}.body{body_extension(resp)}", resp.body)
    summary = f"HTTP {resp.status}"

    location = resp.headers.get("Location")
    if 300 <= resp.status < 400 and location:
        target = urllib.parse.urljoin(url, location)
        meta["redirect_target"] = target
        summary += f" -> {target}"
        # Follow one hop, same host only: outbound requests stay on Cobra.
        if urllib.parse.urlsplit(target).netloc == urllib.parse.urlsplit(url).netloc:
            try:
                hop = fetch(target, follow_redirects=False)
                meta["redirect_hop"] = probe_record(hop)
                summary += f" (HTTP {hop.status})"
            except FetchError as err:
                meta["redirect_hop"] = {"error": str(err)}
                summary += " (hop failed)"

    write_json(directory / f"{stem}.meta.json", meta)
    log(f"probe {path}: {summary} -> {stem}.meta.json")
    return True


def run_probe(paths: list[str], base_url: str, out: Path) -> int:
    results = [probe_one(path, base_url, out) for path in paths]
    return EXIT_OK if all(results) else EXIT_FETCH_FAILED


# --- CLI ---------------------------------------------------------------------


def positive_int(value: str) -> int:
    try:
        number = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"not an integer: {value!r}") from None
    if number < 1:
        raise argparse.ArgumentTypeError(f"must be >= 1: {value!r}")
    return number


def interval_seconds(value: str) -> float:
    try:
        seconds = float(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"not a number: {value!r}") from None
    if seconds < MIN_INTERVAL_S:
        raise argparse.ArgumentTypeError(
            f"must be >= {MIN_INTERVAL_S:g} s to keep load on Cobra low: {value!r}"
        )
    return seconds


def probe_path(value: str) -> str:
    """Accept `/tournaments/X` or `tournaments/X`; return it with a leading slash."""
    if re.match(r"^[A-Za-z]:", value):
        # Git Bash (MSYS) rewrites "/tournaments/X" into "C:/.../tournaments/X".
        raise argparse.ArgumentTypeError(
            f"looks like a filesystem path: {value!r}; in Git Bash write the path"
            " without the leading slash (tournaments/HBYM)"
        )
    if value.startswith("//") or "://" in value or not value.strip("/"):
        raise argparse.ArgumentTypeError(
            f"must be a path on the Cobra host, e.g. tournaments/HBYM: {value!r}"
        )
    return "/" + value.lstrip("/")


def base_url(value: str) -> str:
    parts = urllib.parse.urlsplit(value)
    if parts.scheme not in ("http", "https") or not parts.netloc:
        raise argparse.ArgumentTypeError(f"must be an http(s) URL: {value!r}")
    return value.rstrip("/")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Capture raw Cobra tournament JSON snapshots (task T01).",
    )
    parser.add_argument(
        "ids",
        nargs="*",
        type=positive_int,
        metavar="ID",
        help="tournament ID(s) to poll",
    )
    parser.add_argument(
        "--probe",
        nargs="+",
        type=probe_path,
        metavar="PATH",
        help=(
            "fetch PATH(s) once (e.g. tournaments/HBYM) without following redirects"
            " and record the response"
        ),
    )
    parser.add_argument(
        "--interval",
        type=interval_seconds,
        default=DEFAULT_INTERVAL_S,
        help=(
            f"seconds between poll cycles (default {DEFAULT_INTERVAL_S:g},"
            f" minimum {MIN_INTERVAL_S:g})"
        ),
    )
    parser.add_argument(
        "--count",
        type=positive_int,
        help="stop after N poll cycles (default: run until Ctrl+C)",
    )
    parser.add_argument(
        "--once", action="store_true", help="single poll cycle; same as --count 1"
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("snapshots"),
        help="output directory (default: snapshots)",
    )
    parser.add_argument(
        "--base-url",
        type=base_url,
        default=DEFAULT_BASE_URL,
        help=f"default: {DEFAULT_BASE_URL}",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.probe and args.ids:
        parser.error("give either tournament IDs or --probe, not both")
    if not args.probe and not args.ids:
        parser.error("give at least one tournament ID, or --probe PATH")
    if args.once and args.count is not None:
        parser.error("--once and --count are mutually exclusive")

    try:
        if args.probe:
            return run_probe(args.probe, args.base_url, args.out)
        count = 1 if args.once else args.count
        return run_poll(args.ids, args.base_url, args.out, args.interval, count)
    except KeyboardInterrupt:
        log("interrupted, exiting")
        return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
