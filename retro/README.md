# retro

Improvement loop of the harness, fed by rejections.

1. `scripts/gate.py` or a reviewer (qa-tester, sql-reviewer, ticket-reviewer) rejects a slice.
2. The gate appends one row per failed check to `retro/YYYY-MM.md` on its own (date, slice, cause, status suggested). A reviewer rejection is added by hand in the same format. A row that turns out to be noise or misuse is marked refused, never deleted.
3. A suggested rule is only a suggestion. It goes into `~/.claude/CLAUDE.md`, into an agent in `~/.claude/agents/` or into a skill only with the owner's explicit OK, and its status becomes approved.
4. At the turn of the month, read the file, group repeated causes and bring to the owner what is worth becoming a rule. `scripts/metrics.py` shows the most common FAIL reasons to support that reading.

## Format

One file per month, named `YYYY-MM.md`, with one table and one row per rejection:

```
| date | slice | cause | suggested rule | status |
|------|-------|-------|----------------|--------|
| 2026-11-01 | S22 | gate: files: 14 file(s) outside the expected list (outside the list: Program.cs) | | suggested |
```

Status values:

1. suggested: written by the gate or by hand, waiting for the monthly review.
2. approved: the owner said OK and the rule now lives in the instructions, an agent or a skill.
3. refused: noise, misuse or a rule the owner declined. The row stays as history.

No secret values and no customer data in any row.
