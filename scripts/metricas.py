#!/usr/bin/env python3
"""Métricas das fatias a partir do fatias.jsonl gravado pelo gate.py.

Imprime: total de fatias, % PASS de primeira, 5 motivos de FAIL mais comuns.

Uso: python3 -I ~/.claude/scripts/metricas.py [--arquivo <caminho.jsonl>]
"""
import argparse
import json
import sys
from collections import Counter
from pathlib import Path

PADRAO = Path.home() / ".claude" / "metrics" / "fatias.jsonl"


def ler_registros(caminho):
    registros, invalidas = [], 0
    for linha in caminho.read_text(encoding="utf-8", errors="replace").splitlines():
        linha = linha.strip()
        if not linha:
            continue
        try:
            r = json.loads(linha)
        except ValueError:
            invalidas += 1
            continue
        if isinstance(r, dict) and "fatia" in r and "resultado" in r:
            registros.append(r)
        else:
            invalidas += 1
    return registros, invalidas


def main():
    ap = argparse.ArgumentParser(description="métricas das fatias")
    ap.add_argument("--arquivo", default=str(PADRAO))
    args = ap.parse_args()
    caminho = Path(args.arquivo).expanduser()

    if not caminho.is_file() or caminho.stat().st_size == 0:
        print("sem dados ainda")
        return 0
    registros, invalidas = ler_registros(caminho)
    if not registros:
        print("sem dados ainda")
        return 0

    primeira = {}
    for r in registros:
        chave = (r.get("repo", ""), r["fatia"])
        if chave not in primeira or r.get("data", "") < primeira[chave].get("data", ""):
            primeira[chave] = r
    total_fatias = len(primeira)
    pass_primeira = sum(1 for r in primeira.values() if r["resultado"] == "PASS")
    pct = 100.0 * pass_primeira / total_fatias

    motivos = Counter()
    for r in registros:
        for f in r.get("falhas", []):
            motivos[str(f)] += 1

    print(f"arquivo: {caminho}")
    print(f"execuções do gate: {len(registros)}" + (f" ({invalidas} linha(s) inválida(s) ignorada(s))" if invalidas else ""))
    print(f"total de fatias: {total_fatias}")
    print(f"PASS de primeira: {pass_primeira}/{total_fatias} ({pct:.0f}%)")
    if motivos:
        print("motivos de FAIL mais comuns:")
        for motivo, n in motivos.most_common(5):
            print(f"  {n:>3}  {motivo}")
    else:
        print("motivos de FAIL mais comuns: nenhum FAIL registrado")
    return 0


if __name__ == "__main__":
    sys.exit(main())
