# agentic-delivery-harness

A small harness for delivering code with AI agents (Claude Code) under human control. Agents plan and write; a deterministic script checks; a human approves and commits.

## Components

1. Roles with write boundaries (`agents/`). Six role files: `analista-negocio`, `tech-lead` and `ux-ui` are read-only; `dev-backend` and `dev-frontend` edit only the approved slice in the confirmed repo; `qa-tester` writes only inside the test folder. No role commits, pushes or edits local config.
2. Deterministic gate outside the model (`scripts/gate.py`). Plain Python, no model call. It checks `git status` against the list of expected files, new comments in added code lines, possible secrets in added lines (reported as file:line, value never printed), and runs only the build and test commands it is given. Every run appends one line to a JSONL metrics file.
3. Retro loop with human-approved rules (`retro/`). Each gate FAIL appends a row to the month's retro file. A suggested rule is only a suggestion: it becomes a rule in an agent or in the global instructions only after the owner says OK.

The end-to-end flow is in `docs/flow.md`. `scripts/harness-lint.py` checks the instruction files themselves (broken paths, line limits, memory index, credentials).

## Running the gate

From the `gate.py` docstring:

```
Uso: python3 -I ~/.claude/scripts/gate.py --repo <caminho> --fatia <nome>
        [--esperados <arquivo.txt>] [--build "<cmd>"] [--test "<cmd>"] [--sem-build]
        [--metricas <arquivo.jsonl>] [--retro-dir <pasta>]
Saída: 0 se todos PASS, 1 se algum FAIL.
```

The scripts expect to live in `~/.claude/scripts/`; `--metricas` and `--retro-dir` point the output elsewhere. Metrics summary:

```
python3 -I scripts/metricas.py --arquivo metrics/fatias_anonimizado.jsonl
```

## Reading the retro

1. `retro/README.md` describes the cycle (in Portuguese).
2. Each `retro/YYYY-MM.md` is a table: date, slice, cause, suggested rule, status (sugerida, aprovada, recusada).
3. Noise or misuse is marked recusada, never deleted. At month end, repeated causes are grouped and taken to the owner.
4. `metrics/fatias_anonimizado.jsonl` and `metrics/resumo.md` hold the real gate runs behind those rows. Slices are S01..S22 and repos R1..R4, in order of first appearance; file paths were removed.

## Notice

This is a practitioner's artifact, not a product. The agent texts and scripts are in Portuguese because that is how they run day to day; each agent has an English summary at the top of its body. Names of companies, clients and projects were removed. Expect to adapt paths and rules to your own setup.

## License

MIT, see `LICENSE`.

Author: Kleber Tomazi, KLT Development Ltda.
