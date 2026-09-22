# Clutch OS V3.3 — Trading & Operations

Esta versão evolui diretamente a V3.2 e mantém o banco/configurações existentes.

## Principais mudanças
- Confirmação de encomenda agora mostra ao cliente o resumo completo do pedido.
- Encomendas possuem máquina de estados: OPEN → SEARCHING → FOUND → PROPOSAL_SENT → CUSTOMER_ACCEPTED → AWAITING_ACQUISITION → ACQUIRED → TRADE_LOCK → READY → DELIVERED.
- Operations Center exibe responsável, prioridade e botão de próxima etapa para encomendas.
- `/encomenda-etapa` permite avanço administrativo com custo encontrado, preço ao cliente, fornecedor e Trade Lock.
- Cliente recebe DM nas mudanças relevantes de estado.
- Cancelamento pelo cliente é permitido apenas nas etapas iniciais.
- Trade-In real com `NEG-XXXXX`, itens `TI-XXXXX`, crédito em skins e complemento em dinheiro.
- Skin recebida em Trade-In vira `SK-XXXXX` mantendo custo-base e origem.
- Pagamento de complemento gera lançamento financeiro separado.
- API ganhou `/api/v1/orders/{guild_id}` e `/api/v1/negotiations/{guild_id}`.
- Migração aditiva automática para bancos V3.2 existentes (sem apagar dados).

## Fluxo de Trade-In
1. `/tradein-criar`
2. `/tradein-item` para cada skin recebida
3. `/tradein-pagamento` para PIX/dinheiro recebido
4. `/tradein-receber` quando a skin entrar de fato no estoque

## Exemplo da primeira negociação real
Pode ser modelada como venda de R$ 7.500, crédito de Trade-In de R$ 4.500 e complemento de R$ 3.000, vinculando as encomendas envolvidas e cadastrando Karambit/luvas como itens recebidos separadamente.

## Antes da produção
A V3.3 é a etapa funcional. A próxima V3.4 deve focar exclusivamente em Production Hardening: migrations formais/Alembic, PostgreSQL, idempotência, RBAC, locks, Redis/workers, observabilidade, backup/restore, staging e Production Gate.
