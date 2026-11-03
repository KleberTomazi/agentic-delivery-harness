#!/usr/bin/env python3
"""Gate determinístico de uma fatia (somente leitura no repo).

Confere, nesta ordem:
  a) git status: com --esperados, arquivo fora da lista reprova; sem, só lista.
     Caminhos em obj/, bin/ e demais pastas de IGNORAR_DIRS não contam como fora da lista.
  b) Comentário novo nas linhas adicionadas de código (.cs .ts .tsx .js .jsx .py .sql .css, <!-- em html).
  c) Segredo nas linhas adicionadas (reporta arquivo:linha e tipo, nunca o valor).
     Pula arquivos modelo (.exemplo .example .sample .template .dist, pastas Modelos/ e docs/);
     em .md e .txt só valem as regras de bearer e connection string;
     placeholder (vazio, ${...}, {{...}}, __x__, <...>, TROCAR, SUA_SENHA etc.) não reprova.
  d) Build e teste, só com os comandos passados; nenhum comando é inventado.

Uso: python3 -I ~/.claude/scripts/gate.py --repo <caminho> --fatia <nome>
        [--esperados <arquivo.txt>] [--build "<cmd>"] [--test "<cmd>"] [--sem-build]
        [--metricas <arquivo.jsonl>] [--retro-dir <pasta>]
Saída: 0 se todos PASS, 1 se algum FAIL.
Anexa uma linha em ~/.claude/metrics/fatias.jsonl (ou --metricas) com data, fatia, repo,
resultado, falhas e detalhes (motivo e até 10 linhas por item reprovado, segredo sempre mascarado).
Em FAIL, anexa uma linha por item reprovado em ~/.claude/retro/AAAA-MM.md (ou --retro-dir),
criando o arquivo do mês com cabeçalho e tabela se não existir.
"""
import argparse
import json
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

HOME = Path.home()
METRICAS = HOME / ".claude" / "metrics" / "fatias.jsonl"
RETRO_DIR = HOME / ".claude" / "retro"
MAX_LINHAS_DETALHE = 10
TIMEOUT_S = 600
TAMANHO_MAX_TEXTO = 80
LIMITE_BYTES_ARQUIVO = 2_000_000

EXT_CODIGO = {".cs", ".ts", ".tsx", ".js", ".jsx", ".py", ".sql", ".css"}
EXT_HTML = {".html", ".htm"}
IGNORAR_DIRS = {"node_modules", ".git", "obj", "bin", "dist", "build", ".vs", ".idea"}

DIRETIVAS = ("#region", "#endregion", "#if", "#elif", "#else", "#endif", "#pragma",
             "#nullable", "#define", "#undef", "#line", "#error", "#warning", "#!", "# -*-")
RX_LICENCA = re.compile(r"(?i)copyright|licen[cs]|all rights reserved|spdx-")

RX_HUNK = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@")

SEGREDOS_CHAVE = [
    ("senha/password", re.compile(r"(?i)\b(senha|password|passwd|pwd)\b[\"']?\s*[:=]\s*(.*)$")),
    ("token/apikey/secret", re.compile(r"(?i)\b(token|api[_-]?key|secret|client[_-]?secret)\b[\"']?\s*[:=]\s*(.*)$")),
]
RX_BEARER = re.compile(r"(?i)\bbearer\s+([A-Za-z0-9_\-\.=]{20,})")
RX_CONN = re.compile(r"(?i)\bpassword=([^;\"'\s]{3,})")
RX_LITERAL = re.compile(r"""^["']([^"']{4,})["']""")
RX_PLACEHOLDER = re.compile(r"(?i)^$|^[<{$%@]|^__.*__$|^[\*xX]{3,}$|^(string|null|none|true|false|senha|password|placeholder|changeme|xxx+)$")
RX_PLACEHOLDER_PALAVRA = re.compile(r"(?i)trocar|troque|sua_senha|seu_token|informar|preencher")
SUFIXOS_MODELO = (".exemplo", ".example", ".sample", ".template", ".dist")
PASTAS_MODELO = ("/Modelos/", "/modelos/", "/docs/")
EXT_TEXTO = {".md", ".txt"}


class Item:
    def __init__(self, nome):
        self.nome = nome
        self.ok = True
        self.motivo = ""
        self.detalhes = []

    def falha(self, motivo):
        self.ok = False
        self.motivo = motivo

    def imprimir(self):
        print(f"{'PASS' if self.ok else 'FAIL'}  {self.nome}: {self.motivo}")
        for d in self.detalhes:
            print(f"      {d}")


def git(repo, *args):
    r = subprocess.run(["git", "-c", "core.quotePath=false", "-C", str(repo), *args],
                       capture_output=True, text=True, errors="replace")
    if r.returncode != 0:
        raise RuntimeError(r.stderr.strip().splitlines()[-1] if r.stderr.strip() else f"git {args[0]} falhou")
    return r.stdout


def status_repo(repo):
    saida = git(repo, "status", "--porcelain=v1", "-z", "--untracked-files=all")
    campos = saida.split("\0")
    alterados, nao_rastreados = [], []
    i = 0
    while i < len(campos):
        entrada = campos[i]
        i += 1
        if not entrada:
            continue
        codigo, caminho = entrada[:2], entrada[3:]
        if "R" in codigo or "C" in codigo:
            i += 1
        if codigo == "??":
            nao_rastreados.append(caminho)
        else:
            alterados.append(caminho)
    return alterados, nao_rastreados


def ler_esperados(caminho):
    linhas = Path(caminho).expanduser().read_text(encoding="utf-8", errors="replace").splitlines()
    esperados = []
    for l in linhas:
        l = l.strip()
        if not l or l.startswith("#"):
            continue
        if l.startswith("./"):
            l = l[2:]
        esperados.append(l)
    return esperados


def esperado(caminho, esperados):
    for e in esperados:
        if caminho == e or (e.endswith("/") and caminho.startswith(e)):
            return True
    return False


def em_pasta_ignorada(caminho):
    return any(parte in IGNORAR_DIRS for parte in Path(caminho).parts)


def checar_status(repo, args):
    item = Item("status")
    alterados, nao_rastreados = status_repo(repo)
    todos = alterados + nao_rastreados
    if not todos:
        item.motivo = "working tree limpo"
        return item, alterados, nao_rastreados
    if args.esperados:
        esperados = ler_esperados(args.esperados)
        ignorados = [c for c in todos if em_pasta_ignorada(c) and not esperado(c, esperados)]
        conferidos = [c for c in todos if c not in ignorados]
        fora = [c for c in conferidos if not esperado(c, esperados)]
        faltando = [e for e in esperados if not e.endswith("/") and e not in todos]
        if fora:
            item.falha(f"{len(fora)} arquivo(s) fora da lista de esperados")
            item.detalhes += [f"fora da lista: {c}" for c in fora]
        else:
            item.motivo = f"{len(conferidos)} arquivo(s), todos na lista de esperados"
        item.detalhes += [f"esperado e sem alteração: {e}" for e in faltando]
        if ignorados:
            item.detalhes.append(f"{len(ignorados)} caminho(s) em obj/bin ignorado(s)")
    else:
        item.motivo = f"{len(alterados)} alterado(s), {len(nao_rastreados)} não rastreado(s) (sem --esperados, só listando)"
        item.detalhes += [f"alterado: {c}" for c in alterados]
        item.detalhes += [f"não rastreado: {c}" for c in nao_rastreados]
    return item, alterados, nao_rastreados


def linhas_do_diff(texto):
    adicionadas = {}
    caminho, n = None, 0
    for linha in texto.splitlines():
        if linha.startswith("+++ "):
            alvo = linha[4:]
            caminho = None if alvo == "/dev/null" else (alvo[2:] if alvo.startswith("b/") else alvo)
            continue
        if linha.startswith("--- ") or linha.startswith("diff --git") or linha.startswith("\\ "):
            continue
        m = RX_HUNK.match(linha)
        if m:
            n = int(m.group(1))
            continue
        if caminho is None:
            continue
        if linha.startswith("+"):
            adicionadas.setdefault(caminho, []).append((n, linha[1:]))
            n += 1
        elif linha.startswith(" "):
            n += 1
    return adicionadas


def linhas_nao_rastreadas(repo, caminhos):
    adicionadas = {}
    for c in caminhos:
        p = repo / c
        if any(parte in IGNORAR_DIRS for parte in Path(c).parts):
            continue
        if not p.is_file() or p.stat().st_size > LIMITE_BYTES_ARQUIVO:
            continue
        bruto = p.read_bytes()
        if b"\0" in bruto[:8000]:
            continue
        texto = bruto.decode("utf-8", errors="replace")
        adicionadas[c] = list(enumerate(texto.splitlines(), 1))
    return adicionadas


def juntar(*dicts):
    total = {}
    for d in dicts:
        for caminho, linhas in d.items():
            vistas = set(total.get(caminho, []))
            total[caminho] = sorted(vistas | set(linhas))
    return total


def coletar_adicionadas(repo, nao_rastreados):
    unstaged = linhas_do_diff(git(repo, "diff", "--no-color", "--no-ext-diff", "-U0"))
    staged = linhas_do_diff(git(repo, "diff", "--cached", "--no-color", "--no-ext-diff", "-U0"))
    novos = linhas_nao_rastreadas(repo, nao_rastreados)
    return juntar(unstaged, staged, novos)


def ignorar_comentario(s):
    baixo = s.lower()
    if baixo.startswith(DIRETIVAS):
        return True
    if baixo.startswith("///") and "<reference" in baixo:
        return True
    return bool(RX_LICENCA.search(baixo))


def eh_comentario(ext, texto):
    s = texto.strip()
    if not s or ignorar_comentario(s):
        return False
    if ext == ".py":
        return s.startswith("#")
    if ext == ".sql":
        return s.startswith(("--", "/*", "* ", "*/")) or s == "*"
    if ext in EXT_HTML:
        return s.startswith("<!--")
    if ext == ".css" and "{" in s:
        return False
    if s.startswith("* ") and s.endswith("{"):
        return False
    return s.startswith(("//", "/*", "{/*", "* ", "*/")) or s == "*"


def resumo_linha(texto):
    s = texto.strip()
    if len(s) > TAMANHO_MAX_TEXTO:
        return "(linha longa, texto omitido)"
    return s


def checar_comentarios(adicionadas):
    item = Item("comentarios")
    achados = []
    for caminho, linhas in adicionadas.items():
        ext = Path(caminho).suffix.lower()
        if ext not in EXT_CODIGO and ext not in EXT_HTML:
            continue
        for n, texto in linhas:
            if eh_comentario(ext, texto):
                achados.append(f"{caminho}:{n}  {resumo_linha(texto)}")
    if achados:
        item.falha(f"{len(achados)} comentário(s) novo(s) em código")
        item.detalhes = achados
    else:
        item.motivo = "nenhum comentário novo em código"
    return item


def eh_placeholder(valor):
    valor = valor.strip().strip("\"'")
    return bool(RX_PLACEHOLDER.match(valor) or RX_PLACEHOLDER_PALAVRA.search(valor))


def valor_suspeito(resto, ext):
    resto = resto.strip()
    m = RX_LITERAL.match(resto)
    if m:
        valor = m.group(1)
    elif ext in EXT_CODIGO:
        return False
    else:
        valor = resto.split()[0] if resto.split() else ""
        valor = valor.rstrip(",;")
        if len(valor) < 4:
            return False
    return not eh_placeholder(valor)


def tipos_segredo(texto, ext):
    tipos = []
    if ext not in EXT_TEXTO:
        for nome, rx in SEGREDOS_CHAVE:
            m = rx.search(texto)
            if m and valor_suspeito(m.group(2), ext):
                tipos.append(nome)
    m = RX_BEARER.search(texto)
    if m and not eh_placeholder(m.group(1)):
        tipos.append("bearer")
    m = RX_CONN.search(texto)
    if m and not eh_placeholder(m.group(1)):
        tipos.append("connection string")
    return tipos


def arquivo_modelo(caminho):
    if caminho.lower().endswith(SUFIXOS_MODELO):
        return True
    completo = "/" + caminho
    return any(p in completo for p in PASTAS_MODELO)


def checar_segredos(adicionadas):
    item = Item("segredos")
    achados = []
    for caminho, linhas in adicionadas.items():
        ext = Path(caminho).suffix.lower()
        if any(parte in caminho.lower() for parte in ("/i18n/", "/translations/", "/locales/")):
            continue
        if arquivo_modelo(caminho):
            continue
        for n, texto in linhas:
            tipos = tipos_segredo(texto, ext)
            if tipos:
                achados.append(f"{caminho}:{n}  possível segredo ({', '.join(tipos)}), valor omitido")
    if achados:
        item.falha(f"{len(achados)} possível(is) segredo(s) nas linhas adicionadas")
        item.detalhes = achados
    else:
        item.motivo = "nenhum segredo nas linhas adicionadas"
    return item


def ultima_linha_util(saida):
    linhas = [l.strip() for l in saida.splitlines() if l.strip()]
    for l in reversed(linhas):
        if re.search(r"(?i)\berror\b|\berro\b|failed|falh|exception", l):
            return l[:200]
    return linhas[-1][:200] if linhas else "sem saída"


def rodar_comando(nome, cmd, repo):
    item = Item(nome)
    try:
        r = subprocess.run(cmd, shell=True, cwd=str(repo), capture_output=True,
                           text=True, errors="replace", timeout=TIMEOUT_S)
    except subprocess.TimeoutExpired:
        item.falha(f"timeout de {TIMEOUT_S} s")
        return item
    if r.returncode != 0:
        item.falha(f"exit {r.returncode}")
        item.detalhes = [ultima_linha_util(r.stderr + "\n" + r.stdout)]
    else:
        item.motivo = f"ok ({cmd})"
    return item


def checar_build_teste(repo, args):
    itens = []
    if args.sem_build:
        i = Item("build/teste")
        i.motivo = "pulado (--sem-build)"
        return [i]
    if not args.build and not args.test:
        i = Item("build/teste")
        i.motivo = "build/teste não informados"
        return [i]
    if args.build:
        itens.append(rodar_comando("build", args.build, repo))
    if args.test:
        itens.append(rodar_comando("teste", args.test, repo))
    return itens


def repo_curto(repo):
    try:
        return "~/" + repo.relative_to(HOME).as_posix()
    except ValueError:
        return repo.as_posix()


def registrar(repo, fatia, itens, metricas):
    reprovados = [i for i in itens if not i.ok]
    registro = {
        "data": datetime.now().astimezone().isoformat(timespec="seconds"),
        "fatia": fatia,
        "repo": repo_curto(repo),
        "resultado": "FAIL" if reprovados else "PASS",
        "falhas": [i.nome for i in reprovados],
        "detalhes": {i.nome: {"motivo": i.motivo, "linhas": i.detalhes[:MAX_LINHAS_DETALHE]}
                     for i in reprovados},
    }
    metricas.parent.mkdir(parents=True, exist_ok=True)
    with metricas.open("a", encoding="utf-8") as f:
        f.write(json.dumps(registro, ensure_ascii=False) + "\n")


def celula(texto):
    return " ".join(texto.replace("|", "/").split())


def cabecalho_retro(mes):
    return (f"# retro {mes}\n\n"
            "Reprovações relevantes do gate e dos revisores neste mês. "
            "Regra sugerida só vira regra com OK do Kleber (ver README.md).\n\n"
            "| data | fatia | causa | regra sugerida | status |\n"
            "|------|-------|-------|----------------|--------|\n")


def anexar_retro(fatia, itens, retro_dir):
    reprovados = [i for i in itens if not i.ok]
    if not reprovados:
        return
    agora = datetime.now()
    arquivo = retro_dir / f"{agora:%Y-%m}.md"
    linhas = []
    for i in reprovados:
        causa = f"gate: {i.nome}: {i.motivo}"
        if i.detalhes:
            causa += f" ({i.detalhes[0]})"
        linhas.append(f"| {agora:%Y-%m-%d} | {celula(fatia)} | {celula(causa)} | | sugerida |")
    retro_dir.mkdir(parents=True, exist_ok=True)
    atual = arquivo.read_text(encoding="utf-8") if arquivo.exists() else cabecalho_retro(f"{agora:%Y-%m}")
    arquivo.write_text(atual.rstrip("\n") + "\n" + "\n".join(linhas) + "\n", encoding="utf-8")
    print(f"retro: {len(linhas)} linha(s) anexada(s) em {arquivo}")


def main():
    ap = argparse.ArgumentParser(description="gate determinístico de uma fatia")
    ap.add_argument("--repo", required=True)
    ap.add_argument("--fatia", required=True)
    ap.add_argument("--esperados")
    ap.add_argument("--build")
    ap.add_argument("--test")
    ap.add_argument("--sem-build", action="store_true")
    ap.add_argument("--metricas", default=str(METRICAS))
    ap.add_argument("--retro-dir", default=str(RETRO_DIR))
    args = ap.parse_args()

    repo = Path(args.repo).expanduser().resolve()
    if not repo.is_dir():
        print(f"FAIL  repo: pasta não existe: {repo}")
        return 1
    try:
        raiz = git(repo, "rev-parse", "--show-toplevel").strip()
    except RuntimeError as e:
        print(f"FAIL  repo: não é repositório git ({e})")
        return 1
    repo = Path(raiz)

    print(f"gate: fatia '{args.fatia}' em {repo_curto(repo)}")
    itens = []
    try:
        item_status, alterados, nao_rastreados = checar_status(repo, args)
        itens.append(item_status)
        adicionadas = coletar_adicionadas(repo, nao_rastreados)
        itens.append(checar_comentarios(adicionadas))
        itens.append(checar_segredos(adicionadas))
        itens += checar_build_teste(repo, args)
    except RuntimeError as e:
        i = Item("git")
        i.falha(str(e))
        itens.append(i)

    for i in itens:
        i.imprimir()
    falhas = [i.nome for i in itens if not i.ok]
    print(f"resultado: {'FAIL (' + ', '.join(falhas) + ')' if falhas else 'PASS'}")
    registrar(repo, args.fatia, itens, Path(args.metricas).expanduser())
    anexar_retro(args.fatia, itens, Path(args.retro_dir).expanduser())
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(main())
