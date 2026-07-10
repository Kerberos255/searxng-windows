#!/usr/bin/env python3
"""Query the local OpenClaw SearXNG instance."""

import argparse
import json
import os
import sys
from urllib.parse import urljoin

import httpx


DEFAULT_URL = "http://127.0.0.1:8888"


def search(
    query,
    limit=10,
    category="general",
    language="",
    time_range=None,
    date_after=None,
    date_before=None,
    timeout=80,
):
    base_url = os.environ.get("SEARXNG_URL", DEFAULT_URL).rstrip("/") + "/"
    params = {
        "q": query,
        "format": "json",
        "categories": category,
    }
    if language:
        params["language"] = language
    if time_range:
        params["time_range"] = time_range
    if date_after:
        params["date_after"] = date_after
    if date_before:
        params["date_before"] = date_before

    response = httpx.get(
        urljoin(base_url, "search"),
        params=params,
        timeout=timeout,
        verify=False,
        trust_env=False,
    )
    response.raise_for_status()
    data = response.json()
    data["results"] = data.get("results", [])[:limit]
    return data


def print_table(data):
    results = data.get("results", [])
    if not results:
        print("No results.")
    for idx, item in enumerate(results, 1):
        title = item.get("title", "")
        url = item.get("url", "")
        engine = item.get("engine") or ",".join(item.get("engines", []))
        content = (item.get("content") or "").replace("\n", " ")
        print(f"{idx}. {title}")
        print(f"   {url}")
        if engine:
            print(f"   engine: {engine}")
        if content:
            print(f"   {content[:240]}")
    unresponsive = data.get("unresponsive_engines") or []
    if unresponsive:
        print("\nUnresponsive engines:")
        for item in unresponsive:
            print(f"  - {item}")


def main():
    parser = argparse.ArgumentParser(description="Search via local SearXNG.")
    sub = parser.add_subparsers(dest="command")
    search_parser = sub.add_parser("search")
    search_parser.add_argument("query", nargs="+")
    search_parser.add_argument("-n", "--limit", type=int, default=10)
    search_parser.add_argument("-c", "--category", default="general")
    search_parser.add_argument("-l", "--language", default="")
    search_parser.add_argument("-t", "--time-range", choices=["day", "week", "month", "year"])
    search_parser.add_argument("--date-after", help="Inclusive YYYY-MM-DD start date")
    search_parser.add_argument("--date-before", help="Inclusive YYYY-MM-DD end date")
    search_parser.add_argument("--timeout", type=float, default=80)
    search_parser.add_argument("-f", "--format", choices=["table", "json"], default="table")
    args = parser.parse_args()

    if args.command != "search":
        parser.print_help()
        return 2

    try:
        data = search(
            " ".join(args.query),
            limit=args.limit,
            category=args.category,
            language=args.language,
            time_range=args.time_range,
            date_after=args.date_after,
            date_before=args.date_before,
            timeout=args.timeout,
        )
    except Exception as exc:
        print(f"SearXNG search failed: {exc}", file=sys.stderr)
        return 1

    if args.format == "json":
        print(json.dumps(data, ensure_ascii=False, indent=2))
    else:
        print_table(data)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
