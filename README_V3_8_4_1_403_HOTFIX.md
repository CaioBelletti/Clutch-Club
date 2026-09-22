# Clutch OS V3.8.4.1 — Buylist 403 Hotfix

- Remove alteração automática de permission overwrites do canal Buylist no boot.
- `BUYLIST_ENABLED=false` continua bloqueando novas Buylist no backend e desativando atalhos/painel.
- Histórico e dados permanecem preservados.
- A visibilidade do canal no Discord passa a ser configuração manual, evitando `403 Missing Permissions`.
- Nenhuma migração destrutiva e nenhuma alteração nos fluxos de venda, catálogo, encomenda, financeiro, Inspect ou PostgreSQL.
