#!/usr/bin/env python3
"""Slice metrics from the slices.jsonl written by gate.py.

Prints: gate runs, slices, first-pass rate, top FAIL reasons (up to 5).

Usage: python3 -I ~/.claude/scripts/metrics.py [--file <path.jsonl>]
"""
import argparse
import json
import sys
from collections import Counter
from pathlib import Path

DEFAULT = Path.home() / ".claude" / "metrics" / "slices.jsonl"


def read_entries(path):
    entries, invalid = [], 0
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            r = json.loads(line)
        except ValueError:
            invalid += 1
            continue
        if isinstance(r, dict) and "slice" in r and "result" in r:
            entries.append(r)
        else:
            invalid += 1
    return entries, invalid


def main():
    ap = argparse.ArgumentParser(description="slice metrics from the gate log")
    ap.add_argument("--file", default=str(DEFAULT), help="JSONL file written by gate.py")
    args = ap.parse_args()
    path = Path(args.file).expanduser()

    if not path.is_file() or path.stat().st_size == 0:
        print("no data yet")
        return 0
    entries, invalid = read_entries(path)
    if not entries:
        print("no data yet")
        return 0

    first = {}
    for r in entries:
        key = (r.get("repo", ""), r["slice"])
        if key not in first or r.get("date", "") < first[key].get("date", ""):
            first[key] = r
    total_slices = len(first)
    first_pass = sum(1 for r in first.values() if r["result"] == "PASS")
    pct = 100.0 * first_pass / total_slices

    reasons = Counter()
    for r in entries:
        for f in r.get("failures", []):
            reasons[str(f)] += 1

    print(f"file: {path}")
    print(f"gate runs: {len(entries)}" + (f" ({invalid} invalid line(s) ignored)" if invalid else ""))
    print(f"slices: {total_slices}")
    print(f"first-pass rate: {first_pass}/{total_slices} ({pct:.0f}%)")
    if reasons:
        print("top FAIL reasons:")
        for reason, n in reasons.most_common(5):
            print(f"  {n:>3}  {reason}")
    else:
        print("top FAIL reasons: no FAIL recorded")
    return 0


if __name__ == "__main__":
    sys.exit(main())
