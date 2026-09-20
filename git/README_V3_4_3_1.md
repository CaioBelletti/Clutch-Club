# Clutch OS V3.4.3.1 — Canonical Guild + Exclusive DB

Hotfix de integridade para o ambiente local do Clutch Club.

- Guild canônica: `CANONICAL_GUILD_ID` > `GUILD_ID` > fallback de recuperação do Clutch Club.
- Repara aliases de guild em Orders, Operations, configurações, painéis e demais tabelas com `guild_id`.
- Clientes e configurações usam merge seguro para respeitar constraints únicas.
- Aborta antes da migração se a porta do Control Center já estiver em uso por outra versão.
- Se o Windows bloquear a promoção do SQLite, a migração é cancelada sem iniciar API/Bot.
- Backup do banco canônico continua obrigatório antes da promoção.

Primeiro teste: feche todas as versões antigas do Clutch OS e execute `INICIAR.bat`. Não crie uma nova ENC até validar Operations/Reconciliation/System.
