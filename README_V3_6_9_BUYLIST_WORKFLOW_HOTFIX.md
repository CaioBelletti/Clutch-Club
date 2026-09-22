# Clutch OS V3.6.9 — Buylist Workflow Hotfix

- Corrige AÇÃO / PRÓXIMA ETAPA em BUYLIST: não encerra mais automaticamente.
- PENDING/COUNTERED abre modal de proposta.
- PROPOSED aguarda decisão do cliente.
- ACCEPTED orienta recebimento; RECEIVED orienta PIX; PAID orienta entrada em estoque.
- DONE só é aplicado após estado terminal (COMPLETED/REJECTED/EXPIRED).
- Aceite do cliente devolve a operação para ACTION_REQUIRED e atualiza o card.
- Operações não-ORDER sem workflow explícito não são mais encerradas automaticamente.
- Mantém banco canônico externo e dados existentes.
