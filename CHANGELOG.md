# Changelog

## 0.2.0 (2026-11-05)
- `scripts/gate.py`: optional `--model` and `--tool-version` arguments, recorded as `model` and `tool_version` in every metrics line (null when not given). Added in response to the editorial review of the companion technical report: model versions were not logged during the measured period.
- Documentation: README and metrics/README state that the published log predates these fields.

## 0.1.0 (2026-11-03)
- First public release: agent definitions, gate, metrics and lint scripts, anonymized metrics log, retrospective tables, flow and SQL guardrail documents.
