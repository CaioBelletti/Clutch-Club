# CLUTCH OS V3.8.4.2 — Buylist 403 Hotfix

- Buylist pausada é 100% lógica; o boot não altera overwrites/permissões do canal de Buylist.
- `BUYLIST_ENABLED=false` bloqueia novas Buylist no backend e remove atalhos públicos, preservando histórico.
- Marcador explícito de versão no boot para confirmar que o Railway executa este pacote.
- Nenhuma migração destrutiva ou reset de dados.
