# Clutch OS V3.6.2 — Customer Proposal Namespace Hotfix

Correções:
- View da proposta agora carrega e preserva `guild_id`, `order_id` e `code` originais.
- Aceitar proposta em DM não depende mais de `interaction.guild`/`gid(i)`.
- Busca usa ID interno + guild canônica + código + usuário para evitar colisão ou namespace incorreto.
- Segunda leitura após aceitar/recusar usa `order_id + guild_id` original.
- RECUSAR recebeu a mesma correção de namespace.
- Logs de aceite/recusa/expiração usam a guild original da encomenda.
- Mantida normalização UTC de `proposal_expires_at`.
