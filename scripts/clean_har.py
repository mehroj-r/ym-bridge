#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

DEFAULT_DROP_URL_REGEXES = [
    r"https://log\.strm\.yandex\.ru/log(?:\?|$)",
    r"https://yandex\.ru/clck/click(?:\?|$)",
    r"https://report\.appmetrica\.yandex\.net/report(?:\?|$)",
    r"^https?:\/\/android\.httptoolkit\.tech\/.*$",
    "^https?:\/\/egw\.home-gateway\.plus\.yandex\.net\/v1\/plus-state$",
    r"^https?:\/\/ynison\.music\.yandex\.net\/ynison_redirect\.YnisonRedirectService\/GetRedirectToYnison$",
    r"^https?:\/\/frontend\.vh\.yandex\.ru\/uaas\/android_player(?:\?.*)?$",
    r"^https?:\/\/iot\.quasar\.yandex\.ru\/glagol\/user\/info\?scope=audio$",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Remove HAR requests by URL regex before processing.")
    parser.add_argument(
        "input",
        nargs="?",
        type=Path,
        default=Path("requests.har"),
        help="Input HAR file (default: requests.har)",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=None,
        help="Output HAR file (default: <input>.cleaned.har)",
    )
    parser.add_argument(
        "--drop-url-regex",
        action="append",
        default=[],
        help="Regex to remove matching request URLs (repeatable).",
    )
    parser.add_argument(
        "--regex-file",
        type=Path,
        default=None,
        help="File with one drop regex per line (# comments allowed).",
    )
    parser.add_argument(
        "--no-defaults",
        action="store_true",
        help="Disable built-in telemetry cleanup regexes.",
    )
    parser.add_argument(
        "--ignore-case",
        action="store_true",
        help="Match regexes case-insensitively.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be removed without writing output.",
    )
    parser.add_argument(
        "--pretty",
        action="store_true",
        help="Pretty-print JSON output instead of compact JSON.",
    )
    return parser.parse_args()


def load_regex_file(path: Path) -> list[str]:
    patterns: list[str] = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        patterns.append(line)
    return patterns


def compile_patterns(patterns: list[str], ignore_case: bool) -> list[re.Pattern[str]]:
    flags = re.IGNORECASE if ignore_case else 0
    compiled: list[re.Pattern[str]] = []
    for pattern in patterns:
        try:
            compiled.append(re.compile(pattern, flags))
        except re.error as exc:
            raise ValueError(f"Invalid regex {pattern!r}: {exc}") from exc
    return compiled


def default_output_path(input_path: Path) -> Path:
    return input_path.with_name(f"{input_path.stem}.cleaned.har")


def main() -> int:
    args = parse_args()

    if not args.input.exists():
        print(f"Input file not found: {args.input}", file=sys.stderr)
        return 2

    drop_patterns: list[str] = []
    if not args.no_defaults:
        drop_patterns.extend(DEFAULT_DROP_URL_REGEXES)

    if args.regex_file is not None:
        if not args.regex_file.exists():
            print(f"Regex file not found: {args.regex_file}", file=sys.stderr)
            return 2
        drop_patterns.extend(load_regex_file(args.regex_file))

    drop_patterns.extend(args.drop_url_regex)
    if not drop_patterns:
        print(
            "No regexes were provided. Use --drop-url-regex, --regex-file, or keep defaults enabled.",
            file=sys.stderr,
        )
        return 2

    try:
        drop_regexes = compile_patterns(drop_patterns, args.ignore_case)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    try:
        data = json.loads(args.input.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"Invalid HAR JSON: {exc}", file=sys.stderr)
        return 2

    log_obj = data.get("log")
    if not isinstance(log_obj, dict):
        print("Invalid HAR format: missing object 'log'.", file=sys.stderr)
        return 2

    entries = log_obj.get("entries")
    if not isinstance(entries, list):
        print("Invalid HAR format: missing list 'log.entries'.", file=sys.stderr)
        return 2

    kept_entries: list[dict] = []
    removed_by_pattern: Counter[str] = Counter()

    for entry in entries:
        request = entry.get("request", {})
        url = request.get("url", "") if isinstance(request, dict) else ""
        if not isinstance(url, str):
            url = str(url)

        matched_pattern = None
        for regex in drop_regexes:
            if regex.search(url):
                matched_pattern = regex.pattern
                break

        if matched_pattern is None:
            kept_entries.append(entry)
            continue

        removed_by_pattern[matched_pattern] += 1

    removed_count = len(entries) - len(kept_entries)
    print(f"Input entries: {len(entries)}")
    print(f"Removed:       {removed_count}")
    print(f"Kept:          {len(kept_entries)}")

    if removed_by_pattern:
        print("Removed by regex:")
        for pattern, count in removed_by_pattern.most_common():
            print(f"  {count:>4}  {pattern}")

    if args.dry_run:
        print("Dry-run mode: no file written.")
        return 0

    log_obj["entries"] = kept_entries
    output_path = args.output or default_output_path(args.input)

    if args.pretty:
        text = json.dumps(data, ensure_ascii=False, indent=2)
    else:
        text = json.dumps(data, ensure_ascii=False, separators=(",", ":"))

    output_path.write_text(f"{text}\n", encoding="utf-8")
    print(f"Wrote cleaned HAR: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
