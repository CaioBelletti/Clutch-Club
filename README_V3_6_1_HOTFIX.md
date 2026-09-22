# CLUTCH OS V3.6.2 — OPERATIONS HOTFIX

Correções:
- Normalização UTC de `proposal_expires_at` ao aceitar proposta, evitando comparação entre datetime naive e aware.
- A mesma proteção foi aplicada à expiração de propostas de buylist.
- Identificação visual/runtime atualizada para V3.6.2.
- Mantém o banco persistente externo `..\Clutch_OS_DATA\clutch_v2.db`; não apague a pasta `Clutch_OS_DATA`.

Teste recomendado: criar encomenda -> publicar no centro operacional -> assumir -> procurando -> skin encontrada -> enviar proposta -> aceitar/recusar.
