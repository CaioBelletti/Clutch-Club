# Clutch OS V3.3.6.0 — Inventory Sync Fix

Hotfix da V3.3.5.

- Corrige colisão de IDs HTML entre o KPI de capital em estoque e a view Inventory.
- A aba Inventory volta a renderizar a tabela SK-XXXXX.
- Mantém o lifecycle Trade-In validado.
- Adiciona `GET /api/v1/integrity/{guild_id}` para detectar Trade-Ins ACCEPTED sem Skin correspondente.
- Finance continua calculando ativos de Trade-In a partir das SKs reais em estoque.
