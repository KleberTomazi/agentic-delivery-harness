# Metrics

`slices.jsonl` holds the real gate runs recorded between 2026-10-15 and 2026-11-01, one JSON line per run. Slices were renamed S01..S22 and repositories R1..R4, in order of first appearance. File paths and per-line details were removed; only the failure reason is kept.

Each line has `date`, `slice`, `repo`, `result` (PASS or FAIL), `failures` (any of `files`, `comments`, `secrets`) and, in the later runs, `details` with the reason of each failed check. No line in this log has `model` or `tool_version`: those fields were added to the gate in 0.2.0, after the measured period. The role agents ran on the Claude Code model aliases `fable` (business analyst, tech lead) and `sonnet` (developers, QA, UX); exact model versions were not recorded.

## Summary

Command, run from the repository root:

```
python3 -I scripts/metrics.py --file metrics/slices.jsonl
```

Output:

```
file: metrics/slices.jsonl
gate runs: 33
slices: 22
first-pass rate: 10/22 (45%)
top FAIL reasons:
   14  secrets
   11  comments
   10  files
```

"First-pass rate" counts the slices whose first gate run was PASS. A slice marked "no" below has no PASS run in this log.

## Per slice

| slice | failed runs before first pass | passed |
|-------|-------------------------------|--------|
| S01 | 0 | yes |
| S02 | 2 | no |
| S03 | 1 | no |
| S04 | 2 | no |
| S05 | 1 | no |
| S06 | 1 | yes |
| S07 | 2 | no |
| S08 | 1 | yes |
| S09 | 0 | yes |
| S10 | 0 | yes |
| S11 | 0 | yes |
| S12 | 2 | yes |
| S13 | 0 | yes |
| S14 | 0 | yes |
| S15 | 0 | yes |
| S16 | 0 | yes |
| S17 | 0 | yes |
| S18 | 0 | yes |
| S19 | 1 | no |
| S20 | 1 | no |
| S21 | 1 | no |
| S22 | 1 | no |

For slices that never passed, the count is the number of FAIL runs recorded. S19 is a known false positive: the repository had no commit yet, so every file was untracked (see `retro/2026-10.md`).

These numbers come from one practitioner's daily work. They are not a benchmark.
