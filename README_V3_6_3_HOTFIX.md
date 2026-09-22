# Clutch OS V3.6.3 — Order Resolver + Payment Gate + Test Reset

- `/encomenda-etapa` resolve encomendas pela guild canônica e possui fallback seguro por código, com diagnóstico no terminal.
- `trade_lock_ate` aceita `READY`, `DD/MM/AAAA` e `DD/MM/AAAA HH:MM`.
- Fluxo de encomenda inclui PAGAMENTO PENDENTE e PAGAMENTO CONFIRMADO antes da aquisição.
- Novo comando administrativo `/resetar-encomendas-teste confirmacao:APAGAR TESTES` apaga somente encomendas/operations relacionadas e reinicia a numeração em ENC-00001 no SQLite.
- Estoque, vendas, ledger/financeiro, painéis, configurações e demais dados não são apagados pelo reset.
