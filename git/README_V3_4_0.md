# Clutch OS V3.4.1 — Unified Core / Single Source of Truth

## Mudança de arquitetura
- `orders` é a fonte canônica única de encomendas.
- Discord cria Customer + Order + Operation em **uma transação** via `OrderService`.
- Web, Operations, CRM, Trading, Reconciliation e Production Gate leem a mesma tabela `orders`.
- Uma encomenda não pode existir apenas como mensagem do Discord.

## Persistência entre versões
O banco local não fica mais preso à pasta da versão. O launcher usa:

`..\\Clutch_OS_DATA\\clutch_v2.db`

Na primeira execução, o bootstrap cria a base compartilhada e procura bancos `clutch_v2.db` em versões anteriores para recuperar **encomendas ausentes** sem sobrescrever registros canônicos.

## Production Gate
Novas verificações:
- Order Pipeline Integrity
- Single Source of Truth
- CRM ↔ Orders
- NEG ↔ Cliente ↔ Orders
- TI → SK e unicidade
- pagamentos e crédito Trade-In

## Regra de teste
Crie uma encomenda de teste no Discord. O mesmo `ENC-XXXXX` deve aparecer, após atualizar a página, em Operations, Customers e Reconciliation. O Production Gate não pode ficar PRONTO se houver Order sem CRM ou Operation sem Order correspondente.
