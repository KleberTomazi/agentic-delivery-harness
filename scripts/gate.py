#!/usr/bin/env python3
"""Deterministic gate for one slice (read-only on the repo).

Checks, in this order:
  a) files: git status. With --expected, a file outside the list fails; without it, files are only listed.
     Paths under obj/, bin/ and the other IGNORED_DIRS do not count as outside the list.
  b) comments: new comments in added code lines (.cs .ts .tsx .js .jsx .py .sql .css, <!-- in html).
  c) secrets: possible secrets in added lines (reports file:line and type, never the value).
     Skips template files (.exemplo .example .sample .template .dist, Modelos/ and docs/ folders);
     in .md and .txt only the bearer and connection string rules apply;
     placeholders (empty, ${...}, {{...}}, __x__, <...>, changeme, TROCAR, SUA_SENHA etc.) do not fail.
  d) build and test: only with the commands given; no command is ever guessed.

Usage: python3 -I ~/.claude/scripts/gate.py --repo <path> --slice <name>
        [--expected <file.txt>] [--build "<cmd>"] [--test "<cmd>"] [--no-build]
        [--metrics <file.jsonl>] [--retro-dir <folder>]
        [--model <alias or id>] [--tool-version <text>]
Exit code: 0 if every check passes, 1 if any check fails.
Appends one line to ~/.claude/metrics/slices.jsonl (or --metrics) with date, slice, repo,
result, failures, details (reason and up to 10 lines per failed check, secrets always masked),
model and tool_version (the coding-agent model and tool version used for the slice, as given
on the command line; null when not given). Model versions were not logged before 0.2.0.
On FAIL, appends one row per failed check to ~/.claude/retro/YYYY-MM.md (or --retro-dir),
creating the month file with a header and table if it does not exist.
"""
import argparse
import json
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

HOME = Path.home()
METRICS = HOME / ".claude" / "metrics" / "slices.jsonl"
RETRO_DIR = HOME / ".claude" / "retro"
MAX_DETAIL_LINES = 10
TIMEOUT_S = 600
MAX_TEXT_LEN = 80
MAX_FILE_BYTES = 2_000_000

CODE_EXT = {".cs", ".ts", ".tsx", ".js", ".jsx", ".py", ".sql", ".css"}
HTML_EXT = {".html", ".htm"}
IGNORED_DIRS = {"node_modules", ".git", "obj", "bin", "dist", "build", ".vs", ".idea"}

DIRECTIVES = ("#region", "#endregion", "#if", "#elif", "#else", "#endif", "#pragma",
              "#nullable", "#define", "#undef", "#line", "#error", "#warning", "#!", "# -*-")
RX_LICENSE = re.compile(r"(?i)copyright|licen[cs]|all rights reserved|spdx-")

RX_HUNK = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@")

KEY_SECRETS = [
    ("password", re.compile(r"(?i)\b(senha|password|passwd|pwd)\b[\"']?\s*[:=]\s*(.*)$")),
    ("token/apikey/secret", re.compile(r"(?i)\b(token|api[_-]?key|secret|client[_-]?secret)\b[\"']?\s*[:=]\s*(.*)$")),
]
RX_BEARER = re.compile(r"(?i)\bbearer\s+([A-Za-z0-9_\-\.=]{20,})")
RX_CONN = re.compile(r"(?i)\bpassword=([^;\"'\s]{3,})")
RX_LITERAL = re.compile(r"""^["']([^"']{4,})["']""")
RX_PLACEHOLDER = re.compile(r"(?i)^$|^[<{$%@]|^__.*__$|^[\*xX]{3,}$|^(string|null|none|true|false|senha|password|placeholder|changeme|xxx+)$")
RX_PLACEHOLDER_WORD = re.compile(r"(?i)trocar|troque|sua_senha|seu_token|informar|preencher")
TEMPLATE_SUFFIXES = (".exemplo", ".example", ".sample", ".template", ".dist")
TEMPLATE_FOLDERS = ("/Modelos/", "/modelos/", "/docs/")
TEXT_EXT = {".md", ".txt"}


class Check:
    def __init__(self, name):
        self.name = name
        self.ok = True
        self.reason = ""
        self.details = []

    def fail(self, reason):
        self.ok = False
        self.reason = reason

    def show(self):
        print(f"{'PASS' if self.ok else 'FAIL'}  {self.name}: {self.reason}")
        for d in self.details:
            print(f"      {d}")


def git(repo, *args):
    r = subprocess.run(["git", "-c", "core.quotePath=false", "-C", str(repo), *args],
                       capture_output=True, text=True, errors="replace")
    if r.returncode != 0:
        raise RuntimeError(r.stderr.strip().splitlines()[-1] if r.stderr.strip() else f"git {args[0]} failed")
    return r.stdout


def repo_status(repo):
    output = git(repo, "status", "--porcelain=v1", "-z", "--untracked-files=all")
    fields = output.split("\0")
    modified, untracked = [], []
    i = 0
    while i < len(fields):
        entry = fields[i]
        i += 1
        if not entry:
            continue
        code, path = entry[:2], entry[3:]
        if "R" in code or "C" in code:
            i += 1
        if code == "??":
            untracked.append(path)
        else:
            modified.append(path)
    return modified, untracked


def read_expected(path):
    lines = Path(path).expanduser().read_text(encoding="utf-8", errors="replace").splitlines()
    expected = []
    for l in lines:
        l = l.strip()
        if not l or l.startswith("#"):
            continue
        if l.startswith("./"):
            l = l[2:]
        expected.append(l)
    return expected


def is_expected(path, expected):
    for e in expected:
        if path == e or (e.endswith("/") and path.startswith(e)):
            return True
    return False


def in_ignored_dir(path):
    return any(part in IGNORED_DIRS for part in Path(path).parts)


def check_files(repo, args):
    check = Check("files")
    modified, untracked = repo_status(repo)
    everything = modified + untracked
    if not everything:
        check.reason = "working tree clean"
        return check, modified, untracked
    if args.expected:
        expected = read_expected(args.expected)
        ignored = [c for c in everything if in_ignored_dir(c) and not is_expected(c, expected)]
        checked = [c for c in everything if c not in ignored]
        outside = [c for c in checked if not is_expected(c, expected)]
        missing = [e for e in expected if not e.endswith("/") and e not in everything]
        if outside:
            check.fail(f"{len(outside)} file(s) outside the expected list")
            check.details += [f"outside the list: {c}" for c in outside]
        else:
            check.reason = f"{len(checked)} file(s), all in the expected list"
        check.details += [f"expected but unchanged: {e}" for e in missing]
        if ignored:
            check.details.append(f"{len(ignored)} path(s) under obj/bin ignored")
    else:
        check.reason = f"{len(modified)} modified, {len(untracked)} untracked (no --expected, listing only)"
        check.details += [f"modified: {c}" for c in modified]
        check.details += [f"untracked: {c}" for c in untracked]
    return check, modified, untracked


def diff_lines(text):
    added = {}
    path, n = None, 0
    for line in text.splitlines():
        if line.startswith("+++ "):
            target = line[4:]
            path = None if target == "/dev/null" else (target[2:] if target.startswith("b/") else target)
            continue
        if line.startswith("--- ") or line.startswith("diff --git") or line.startswith("\\ "):
            continue
        m = RX_HUNK.match(line)
        if m:
            n = int(m.group(1))
            continue
        if path is None:
            continue
        if line.startswith("+"):
            added.setdefault(path, []).append((n, line[1:]))
            n += 1
        elif line.startswith(" "):
            n += 1
    return added


def untracked_lines(repo, paths):
    added = {}
    for c in paths:
        p = repo / c
        if any(part in IGNORED_DIRS for part in Path(c).parts):
            continue
        if not p.is_file() or p.stat().st_size > MAX_FILE_BYTES:
            continue
        raw = p.read_bytes()
        if b"\0" in raw[:8000]:
            continue
        text = raw.decode("utf-8", errors="replace")
        added[c] = list(enumerate(text.splitlines(), 1))
    return added


def merge(*dicts):
    total = {}
    for d in dicts:
        for path, lines in d.items():
            seen = set(total.get(path, []))
            total[path] = sorted(seen | set(lines))
    return total


def collect_added(repo, untracked):
    unstaged = diff_lines(git(repo, "diff", "--no-color", "--no-ext-diff", "-U0"))
    staged = diff_lines(git(repo, "diff", "--cached", "--no-color", "--no-ext-diff", "-U0"))
    new = untracked_lines(repo, untracked)
    return merge(unstaged, staged, new)


def skip_comment(s):
    low = s.lower()
    if low.startswith(DIRECTIVES):
        return True
    if low.startswith("///") and "<reference" in low:
        return True
    return bool(RX_LICENSE.search(low))


def is_comment(ext, text):
    s = text.strip()
    if not s or skip_comment(s):
        return False
    if ext == ".py":
        return s.startswith("#")
    if ext == ".sql":
        return s.startswith(("--", "/*", "* ", "*/")) or s == "*"
    if ext in HTML_EXT:
        return s.startswith("<!--")
    if ext == ".css" and "{" in s:
        return False
    if s.startswith("* ") and s.endswith("{"):
        return False
    return s.startswith(("//", "/*", "{/*", "* ", "*/")) or s == "*"


def short_line(text):
    s = text.strip()
    if len(s) > MAX_TEXT_LEN:
        return "(long line, text omitted)"
    return s


def check_comments(added):
    check = Check("comments")
    found = []
    for path, lines in added.items():
        ext = Path(path).suffix.lower()
        if ext not in CODE_EXT and ext not in HTML_EXT:
            continue
        for n, text in lines:
            if is_comment(ext, text):
                found.append(f"{path}:{n}  {short_line(text)}")
    if found:
        check.fail(f"{len(found)} new comment(s) in code")
        check.details = found
    else:
        check.reason = "no new comments in code"
    return check


def is_placeholder(value):
    value = value.strip().strip("\"'")
    return bool(RX_PLACEHOLDER.match(value) or RX_PLACEHOLDER_WORD.search(value))


def suspicious_value(rest, ext):
    rest = rest.strip()
    m = RX_LITERAL.match(rest)
    if m:
        value = m.group(1)
    elif ext in CODE_EXT:
        return False
    else:
        value = rest.split()[0] if rest.split() else ""
        value = value.rstrip(",;")
        if len(value) < 4:
            return False
    return not is_placeholder(value)


def secret_types(text, ext):
    types = []
    if ext not in TEXT_EXT:
        for name, rx in KEY_SECRETS:
            m = rx.search(text)
            if m and suspicious_value(m.group(2), ext):
                types.append(name)
    m = RX_BEARER.search(text)
    if m and not is_placeholder(m.group(1)):
        types.append("bearer")
    m = RX_CONN.search(text)
    if m and not is_placeholder(m.group(1)):
        types.append("connection string")
    return types


def is_template(path):
    if path.lower().endswith(TEMPLATE_SUFFIXES):
        return True
    full = "/" + path
    return any(p in full for p in TEMPLATE_FOLDERS)


def check_secrets(added):
    check = Check("secrets")
    found = []
    for path, lines in added.items():
        ext = Path(path).suffix.lower()
        if any(part in path.lower() for part in ("/i18n/", "/translations/", "/locales/")):
            continue
        if is_template(path):
            continue
        for n, text in lines:
            types = secret_types(text, ext)
            if types:
                found.append(f"{path}:{n}  possible secret ({', '.join(types)}), value omitted")
    if found:
        check.fail(f"{len(found)} possible secret(s) in added lines")
        check.details = found
    else:
        check.reason = "no secrets in added lines"
    return check


def last_useful_line(output):
    lines = [l.strip() for l in output.splitlines() if l.strip()]
    for l in reversed(lines):
        if re.search(r"(?i)\berror\b|\berro\b|failed|falh|exception", l):
            return l[:200]
    return lines[-1][:200] if lines else "no output"


def run_command(name, cmd, repo):
    check = Check(name)
    try:
        r = subprocess.run(cmd, shell=True, cwd=str(repo), capture_output=True,
                           text=True, errors="replace", timeout=TIMEOUT_S)
    except subprocess.TimeoutExpired:
        check.fail(f"timeout after {TIMEOUT_S} s")
        return check
    if r.returncode != 0:
        check.fail(f"exit {r.returncode}")
        check.details = [last_useful_line(r.stderr + "\n" + r.stdout)]
    else:
        check.reason = f"ok ({cmd})"
    return check


def check_build_test(repo, args):
    checks = []
    if args.no_build:
        c = Check("build/test")
        c.reason = "skipped (--no-build)"
        return [c]
    if not args.build and not args.test:
        c = Check("build/test")
        c.reason = "no build or test command given"
        return [c]
    if args.build:
        checks.append(run_command("build", args.build, repo))
    if args.test:
        checks.append(run_command("test", args.test, repo))
    return checks


def short_repo(repo):
    try:
        return "~/" + repo.relative_to(HOME).as_posix()
    except ValueError:
        return repo.as_posix()


def record(repo, slice_name, checks, metrics, model=None, tool_version=None):
    failed = [c for c in checks if not c.ok]
    entry = {
        "date": datetime.now().astimezone().isoformat(timespec="seconds"),
        "slice": slice_name,
        "repo": short_repo(repo),
        "result": "FAIL" if failed else "PASS",
        "failures": [c.name for c in failed],
        "details": {c.name: {"reason": c.reason, "lines": c.details[:MAX_DETAIL_LINES]}
                    for c in failed},
        "model": model,
        "tool_version": tool_version,
    }
    metrics.parent.mkdir(parents=True, exist_ok=True)
    with metrics.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def cell(text):
    return " ".join(text.replace("|", "/").split())


def retro_header(month):
    return (f"# retro {month}\n\n"
            "Relevant rejections from the gate and the reviewers this month. "
            "A suggested rule only becomes a rule with the owner's OK (see README.md).\n\n"
            "| date | slice | cause | suggested rule | status |\n"
            "|------|-------|-------|----------------|--------|\n")


def append_retro(slice_name, checks, retro_dir):
    failed = [c for c in checks if not c.ok]
    if not failed:
        return
    now = datetime.now()
    month_file = retro_dir / f"{now:%Y-%m}.md"
    rows = []
    for c in failed:
        cause = f"gate: {c.name}: {c.reason}"
        if c.details:
            cause += f" ({c.details[0]})"
        rows.append(f"| {now:%Y-%m-%d} | {cell(slice_name)} | {cell(cause)} | | suggested |")
    retro_dir.mkdir(parents=True, exist_ok=True)
    current = month_file.read_text(encoding="utf-8") if month_file.exists() else retro_header(f"{now:%Y-%m}")
    month_file.write_text(current.rstrip("\n") + "\n" + "\n".join(rows) + "\n", encoding="utf-8")
    print(f"retro: {len(rows)} row(s) appended to {month_file}")


def main():
    ap = argparse.ArgumentParser(description="deterministic gate for one slice")
    ap.add_argument("--repo", required=True, help="path to the git repository to check")
    ap.add_argument("--slice", required=True, help="slice name recorded in metrics and retro")
    ap.add_argument("--expected", help="text file with the expected changed paths, one per line")
    ap.add_argument("--build", help="build command to run in the repo root")
    ap.add_argument("--test", help="test command to run in the repo root")
    ap.add_argument("--no-build", action="store_true", help="skip build and test")
    ap.add_argument("--metrics", default=str(METRICS), help="JSONL file that receives one line per run")
    ap.add_argument("--retro-dir", default=str(RETRO_DIR), help="folder for the monthly retro files")
    ap.add_argument("--model", help="coding-agent model alias or id used for the slice, recorded in the metrics line")
    ap.add_argument("--tool-version", help="coding tool version used for the slice (for example the output of claude --version)")
    args = ap.parse_args()

    repo = Path(args.repo).expanduser().resolve()
    if not repo.is_dir():
        print(f"FAIL  repo: folder does not exist: {repo}")
        return 1
    try:
        root = git(repo, "rev-parse", "--show-toplevel").strip()
    except RuntimeError as e:
        print(f"FAIL  repo: not a git repository ({e})")
        return 1
    repo = Path(root)

    print(f"gate: slice '{args.slice}' in {short_repo(repo)}")
    checks = []
    try:
        files_check, modified, untracked = check_files(repo, args)
        checks.append(files_check)
        added = collect_added(repo, untracked)
        checks.append(check_comments(added))
        checks.append(check_secrets(added))
        checks += check_build_test(repo, args)
    except RuntimeError as e:
        c = Check("git")
        c.fail(str(e))
        checks.append(c)

    for c in checks:
        c.show()
    failures = [c.name for c in checks if not c.ok]
    print(f"result: {'FAIL (' + ', '.join(failures) + ')' if failures else 'PASS'}")
    record(repo, args.slice, checks, Path(args.metrics).expanduser(), args.model, args.tool_version)
    append_retro(args.slice, checks, Path(args.retro_dir).expanduser())
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
