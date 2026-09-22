# Clutch OS V3.8.1 — Onboarding Access Gate

Hotfix cirúrgico sobre a V3.8.0.

- `ENTRAR PARA O CLUB` continua atribuindo o cargo Cliente.
- Mesmo se o usuário já tiver Cliente, o botão agora reconfere e repara a matriz de acesso.
- Valida os canais públicos e mantém Operations privado.
- Retorna atalhos diretos para Catálogo, Buylist, Lista de Interesse, Encomendas e Avaliações.
- Registra `ONBOARDING_COMPLETE` com resultado da validação.
- Nenhum fluxo de compra, venda, ticket, inspect, financeiro, PostgreSQL ou Control Center foi alterado.

Observação: a personalização visual de canais do próprio Discord pode ocultar um canal da barra lateral mesmo quando o membro tem permissão. Os atalhos diretos reduzem essa dependência sem alterar o restante do servidor.
