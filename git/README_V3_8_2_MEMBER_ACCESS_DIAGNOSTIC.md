# Clutch OS V3.8.2 — Member Access Diagnostic

Hotfix de diagnóstico, sem alterar os fluxos de venda, buylist, encomendas, catálogo, financeiro, Inspect, PostgreSQL ou Control Center.

## Mudanças
- O boot agora registra `[ACCESS MEMBER]` para cada membro real que possui o cargo Cliente.
- A checagem usa `channel.permissions_for(member)`, isto é, a permissão efetiva da conta real.
- O log mostra `@everyone`, overwrites de cargos, overwrite específico do membro e se a conta possui Administrator.
- Novo comando administrativo `/diagnostico-membro @membro` para inspecionar uma conta específica sem alterar permissões.
- Nenhuma permissão é modificada pelo novo diagnóstico.

## Objetivo
Identificar por que uma conta Cliente não recebe/visualiza canais como `skins-disponíveis`, mesmo quando a checagem isolada do cargo Cliente retorna OK.
