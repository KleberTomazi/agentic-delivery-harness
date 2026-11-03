# Examples

`expected-files.txt` is a sample list of the files one slice is allowed to change, one path per line, relative to the repository root. Blank lines and lines starting with `#` are ignored. A line ending in `/` accepts every file under that folder.

Run the gate on a repository with that list, a build command and a test command:

```
python3 -I ~/.claude/scripts/gate.py --repo ~/code/my-service --slice F1-order-total \
  --expected examples/expected-files.txt \
  --build "dotnet build" --test "dotnet test"
```

Any changed file outside the list fails the `files` check. A file in the list that did not change is reported, but does not fail. Use `--no-build` to skip build and test, and `--metrics` and `--retro-dir` to write the run log and the retro rows somewhere other than `~/.claude`.
