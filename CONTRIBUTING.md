# Contributing

Issues and pull requests are welcome: bug reports on the scripts, false positives or misses of the gate, clearer agent texts, and notes on how you adapted the harness to your own setup.

1. Keep changes small and explain the case that motivated them.
2. Never include secrets, tokens, connection strings or internal URLs, not even as examples.
3. Never include customer names, company names or data from real projects. Use generic names (R1, S01, `TargetTable`).
4. Run `python3 -m py_compile scripts/*.py` and, for gate changes, run the gate against a test repository before opening the pull request.
5. Scripts stay in plain Python with no dependencies and no comments in code.

Issues and pull requests can be written in English or Portuguese.
