# Clutch OS V3.5.0 — Production Integrity

Build de estabilização integral.

- Guild canônica Discord: 1549553223470416022.
- Recovery histórico V3.4.5 permanece one-shot e idempotente.
- `/api/v1/diagnostics/{guild}` prova contagens reais do banco e detecta namespaces estrangeiros.
- Dashboard não converte exceções em KPIs R$0. Falha de dados vira erro explícito.
- Production Gate verifica pureza de namespace, CRM↔Order, Order↔Operation, TI↔SK, pagamentos, Trade-In e duplicidade operacional.
- OrderService continua sendo a transação canônica Customer + Order + Operation.
- Inclui `SELF_TEST.bat` / `self_test.py` para smoke/integrity test local sem Discord.
