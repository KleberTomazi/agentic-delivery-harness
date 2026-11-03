# retro

Ciclo de melhoria do harness, alimentado pelas reprovações.

1. O `gate.py` ou um revisor (qa-tester, sql-reviewer, ticket-reviewer) reprova uma fatia.
2. O `gate.py` já anexa sozinho uma linha em `retro/AAAA-MM.md` por item reprovado (data, fatia, causa, status sugerida). Reprovação de revisor (qa-tester, sql-reviewer, ticket-reviewer) entra à mão no mesmo formato. Linha que for ruído ou erro de uso: marcar status recusada, não apagar.
3. Regra sugerida é só sugestão. Só entra em `~/.claude/CLAUDE.md`, num agente de `~/.claude/agents/` ou numa skill com OK explícito do Kleber.
4. Na virada do mês, ler o arquivo, agrupar causas repetidas e levar ao Kleber o que vale virar regra. `metricas.py` mostra os motivos de FAIL mais comuns pra apoiar essa leitura.

Formato de cada arquivo mensal: tabela com colunas data, fatia, causa, regra sugerida, status (sugerida, aprovada, recusada). Uma linha por reprovação. Sem valor de segredo, sem dado de cliente.
