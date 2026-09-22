# Clutch OS V3.6.7 — Launch Readiness

Hotfix final de preparação para inauguração.

- Feedback operacional imediato quando cliente ACEITA ou RECUSA uma proposta de encomenda.
- Recusa preserva o valor recusado no Audit e notifica o Operations Center antes de voltar a PROCURANDO.
- `/diagnostico` agora valida também o acesso efetivo do cargo Cliente aos canais públicos e confirma que Operations Center está oculto.
- Novo `/corrigir-acesso-clientes` sincroniza permissões do cargo Cliente nos canais públicos configurados e protege Operations Center.
- `/configurar-onboarding` também sincroniza a matriz de acesso do Cliente.
- Onboarding permanece visível ao Cliente após a entrada.
- Mantidos banco canônico, financeiro idempotente, Trade Lock e reset de encomendas de teste das versões anteriores.
