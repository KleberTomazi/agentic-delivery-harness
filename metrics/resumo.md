# resumo das métricas

Comando, rodado na raiz desta pasta:

```
python3 -I scripts/metricas.py --arquivo metrics/fatias_anonimizado.jsonl
```

Saída:

```
arquivo: metrics/fatias_anonimizado.jsonl
execuções do gate: 33
total de fatias: 22
PASS de primeira: 10/22 (45%)
motivos de FAIL mais comuns:
   14  segredos
   11  comentarios
   10  status
```
