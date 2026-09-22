# Clutch OS V3.4.3.1 — Forensics + Guild Repair & Production Gate

- Inventaria todos os `clutch_v2.db` históricos encontrados abaixo da pasta `boot`.
- Não escolhe mais um único banco por score: consolida todas as fontes válidas.
- Detecta ENC tanto em `orders` quanto em `operations_queue`.
- Reconstrói uma Order canônica quando uma operação ORDER histórica existe sem Order correspondente.
- Reassocia CRM pelo Discord ID e corrige `Operation.entity_id`.
- Production Gate inclui `Historical Data Completeness`: histórico detectado mas ausente no Core deixa o sistema NÃO PRONTO.
- Version Consistency e todos os rótulos passam a V3.4.3.1.
- Backup antes da promoção e rollback se qualquer ENC histórica detectada continuar ausente.

Primeiro boot: não crie novas encomendas. Valide o bloco `[RECOVERY]` e depois System/Reconciliation/Customers/Operations.
