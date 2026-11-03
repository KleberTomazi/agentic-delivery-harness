#!/usr/bin/env python3
"""Lint for the Claude working harness (read-only).

Checks:
  1. Paths quoted in CLAUDE.md files exist on disk (git refs like origin/... and
     the obj/ and bin/ tokens are not treated as paths).
  2. Line ceiling of each CLAUDE.md (hubs and products have a declared ceiling).
  3. Memory: MEMORY.md links point to existing files, files without an index
     entry (orphans), broken [[links]], and valid frontmatter. The same .md file
     (or the same frontmatter name:) in more than one projects/*/memory/ folder
     is reported as a duplicated memory WARNING.
  4. Credential scan in CLAUDE.md and memory files (reports only
     file:line and the pattern type, never the value).

Usage: python3 ~/.claude/scripts/harness-lint.py [--root ~/Projects]
Exit code: 0 if there are no errors, 1 if there are errors. A WARNING does not fail.
"""
import argparse
import os
import re
import sys
from pathlib import Path

HOME = Path.home()
CLAUDE_HOME = HOME / ".claude"
MEMORY_ROOT = CLAUDE_HOME / "projects"

TETOS = {
    "CLAUDE.md": None,
    "work/CLAUDE.md": 40,
    "personal/CLAUDE.md": 40,
    "CLAUDE.md@raiz": 25,
    "work/<produto>/CLAUDE.md": 70,
}
AVISO_LINHAS = 200

EXT_CAMINHO = (".md", ".txt", ".csv", ".sh", ".py", ".json", ".html", ".bpmn",
               ".png", ".docx", ".sql", ".yml", ".yaml", ".ps1", ".cs", ".ts", ".tsx")

PADROES_CRED = [
    ("password", re.compile(r"(?i)\b(senha|password|passwd|pwd)\s*[:=]\s*\S{4,}")),
    ("token/PAT/apikey", re.compile(r"(?i)\b(token|api[_-]?key|secret|pat)\s*[:=]\s*[A-Za-z0-9_\-\.]{12,}")),
    ("bearer", re.compile(r"(?i)bearer\s+[A-Za-z0-9_\-\.]{12,}")),
    ("connection string", re.compile(r"(?i)password=[^;\s]{3,}")),
]


class Relatorio:
    def __init__(self):
        self.erros = []
        self.avisos = []

    def erro(self, msg):
        self.erros.append(msg)

    def aviso(self, msg):
        self.avisos.append(msg)


def achar_claude_md(raiz):
    arquivos = [CLAUDE_HOME / "CLAUDE.md", raiz / "CLAUDE.md"]
    for sub in ("work", "personal"):
        base = raiz / sub
        if not base.is_dir():
            continue
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames[:] = [d for d in dirnames if d not in ("node_modules", ".git", "obj", "bin")]
            if dirpath[len(str(base)):].count(os.sep) > 3:
                dirnames[:] = []
            if "CLAUDE.md" in filenames:
                arquivos.append(Path(dirpath) / "CLAUDE.md")
    vistos, unicos = set(), []
    for a in arquivos:
        if a.is_file() and a not in vistos:
            vistos.add(a)
            unicos.append(a)
    return unicos


def teto_para(arq, raiz):
    try:
        rel = arq.relative_to(raiz).as_posix()
    except ValueError:
        rel = None
    if arq == raiz / "CLAUDE.md":
        return TETOS["CLAUDE.md@raiz"]
    if rel in TETOS and TETOS[rel] is not None:
        return TETOS[rel]
    return None


EXT_CODIGO = (".cs", ".ts", ".tsx", ".js", ".jsx", ".py", ".sql", ".ps1")
IGNORAR_DIRS = {"node_modules", ".git", "obj", "bin", "dist", "build"}


def existe_em_ancestrais(tok, arq, raiz):
    """Relative path: search from the CLAUDE.md folder up to the root."""
    for pasta in [arq.parent, *arq.parent.parents]:
        if (pasta / tok.rstrip("/")).exists():
            return True
        if pasta in (raiz, HOME):
            break
    return False


def nome_existe_na_arvore(nome, base):
    """Path quoted by name or by its tail: search for a file or folder in any subfolder (up to 6 levels)."""
    base_prof = len(base.parts)
    for dirpath, dirnames, filenames in os.walk(base):
        dirnames[:] = [d for d in dirnames if d not in IGNORAR_DIRS]
        if len(Path(dirpath).parts) - base_prof > 6:
            dirnames[:] = []
        if nome in filenames or nome in dirnames:
            return True
        if Path(dirpath).as_posix().endswith(nome.rstrip("/")):
            return True
    return False


def checar_caminhos(arq, rel, raiz, rep):
    texto = arq.read_text(encoding="utf-8", errors="replace")
    for m in re.finditer(r"`([^`\n]+)`", texto):
        tok = m.group(1).strip()
        if " " in tok or tok.startswith(("http", "$", "-", "~/", "@")):
            continue
        if any(c in tok for c in "<>*|{}()") or "..." in tok or "AAAA" in tok or "@" in tok:
            continue
        if "/" not in tok and not tok.endswith(EXT_CAMINHO):
            continue
        if tok.startswith("origin/") or tok in ("obj/", "bin/"):
            continue
        linha = texto[: m.start()].count("\n") + 1
        if tok.startswith("/Users/"):
            if not Path(tok).exists():
                rep.aviso(f"{rel}:{linha} absolute path does not exist: `{tok}`")
            continue
        if existe_em_ancestrais(tok, arq, raiz):
            continue
        if tok.startswith(("/", ".")):
            continue
        nome = tok.rstrip("/").split("/")[-1]
        if nome_existe_na_arvore(nome, arq.parent):
            continue
        rep.aviso(f"{rel}:{linha} quoted path not found: `{tok}`")


def checar_linhas(arq, rel, raiz, rep):
    n = arq.read_text(encoding="utf-8", errors="replace").count("\n") + 1
    teto = teto_para(arq, raiz)
    if teto is not None and n > teto:
        rep.erro(f"{rel} has {n} lines, declared ceiling is {teto}")
    elif teto is None and n > AVISO_LINHAS:
        rep.aviso(f"{rel} has {n} lines (above {AVISO_LINHAS}, consider trimming)")


def checar_memoria(pasta, rep):
    indice = pasta / "MEMORY.md"
    arquivos = sorted(p for p in pasta.glob("*.md") if p.name != "MEMORY.md")
    nomes = {p.name for p in arquivos}
    if not indice.exists():
        if arquivos:
            rep.erro(f"{pasta.parent.name}: {len(arquivos)} file(s) without MEMORY.md")
        return
    idx = indice.read_text(encoding="utf-8", errors="replace")
    ligados = set()
    for m in re.finditer(r"\]\(([^)\s]+\.md)\)", idx):
        alvo = m.group(1)
        ligados.add(alvo)
        if not (pasta / alvo).exists():
            linha = idx[: m.start()].count("\n") + 1
            rep.erro(f"{pasta.parent.name}/MEMORY.md:{linha} broken link: {alvo}")
    for orfao in sorted(nomes - ligados):
        rep.aviso(f"{pasta.parent.name}: {orfao} has no entry in MEMORY.md")
    for p in arquivos:
        t = p.read_text(encoding="utf-8", errors="replace")
        if not t.startswith("---") or "\nname:" not in t[:500]:
            rep.aviso(f"{pasta.parent.name}/{p.name} has no frontmatter name:")
        for m in re.finditer(r"\[\[([^\]]+)\]\]", t):
            if not (pasta / f"{m.group(1)}.md").exists():
                linha = t[: m.start()].count("\n") + 1
                rep.aviso(f"{pasta.parent.name}/{p.name}:{linha} [[{m.group(1)}]] does not exist")


def nome_frontmatter(texto):
    if not texto.startswith("---"):
        return None
    fim = texto.find("\n---", 3)
    bloco = texto[3:fim] if fim != -1 else texto[3:500]
    for linha in bloco.splitlines():
        if linha.startswith("name:"):
            valor = linha[5:].strip().strip("\"'")
            return valor or None
    return None


def checar_memoria_duplicada(pastas, rep):
    por_arquivo, por_nome = {}, {}
    for pasta in pastas:
        rotulo = pasta.parent.name
        for p in sorted(pasta.glob("*.md")):
            if p.name == "MEMORY.md":
                continue
            por_arquivo.setdefault(p.name, []).append((rotulo, p.name))
            nome = nome_frontmatter(p.read_text(encoding="utf-8", errors="replace"))
            if nome:
                por_nome.setdefault(nome, []).append((rotulo, p.name))
    avisados = set()
    for arquivo, onde in sorted(por_arquivo.items()):
        if len(onde) > 1:
            avisados.add(tuple(sorted(onde)))
            rep.aviso(f"duplicated memory across folders: {arquivo} in {', '.join(r for r, _ in onde)}")
    for nome, onde in sorted(por_nome.items()):
        rotulos = {r for r, _ in onde}
        if len(rotulos) > 1 and tuple(sorted(onde)) not in avisados:
            rep.aviso(f"duplicated memory across folders: {nome} in {', '.join(sorted(rotulos))}")


def varrer_credenciais(arquivos, raiz, rep):
    for arq in arquivos:
        rel = arq.relative_to(raiz) if arq.is_relative_to(raiz) else arq
        for n, linha in enumerate(arq.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
            for nome, rx in PADROES_CRED:
                if rx.search(linha):
                    rep.erro(f"{rel}:{n} possible credential ({nome}), value omitted")
                    break


def main():
    ap = argparse.ArgumentParser(description="lint for the Claude working harness")
    ap.add_argument("--root", default=str(HOME / "Projects"), help="projects root folder (default ~/Projects)")
    args = ap.parse_args()
    raiz = Path(args.root).expanduser().resolve()
    rep = Relatorio()

    claudes = achar_claude_md(raiz)
    for arq in claudes:
        rel = arq.relative_to(HOME) if arq.is_relative_to(HOME) else arq
        checar_linhas(arq, f"~/{rel}" if arq.is_relative_to(HOME) else str(rel), raiz, rep)
        checar_caminhos(arq, str(rel), raiz, rep)

    if MEMORY_ROOT.is_dir():
        pastas_mem = [p for p in sorted(MEMORY_ROOT.glob("*/memory")) if p.is_dir()]
        for pasta in pastas_mem:
            checar_memoria(pasta, rep)
        checar_memoria_duplicada(pastas_mem, rep)
        arquivos_mem = list(MEMORY_ROOT.glob("*/memory/*.md"))
    else:
        arquivos_mem = []

    varrer_credenciais(claudes + arquivos_mem, HOME, rep)

    print(f"harness-lint: {len(claudes)} CLAUDE.md, {len(arquivos_mem)} memory files")
    for e in rep.erros:
        print(f"ERROR   {e}")
    for a in rep.avisos:
        print(f"WARNING {a}")
    print(f"result: {len(rep.erros)} error(s), {len(rep.avisos)} warning(s)")
    return 1 if rep.erros else 0


if __name__ == "__main__":
    sys.exit(main())
