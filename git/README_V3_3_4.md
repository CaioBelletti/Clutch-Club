# Clutch OS V3.3.4 — Operational Web + Trade-In + Finance

## Novidades
- Control Center com abas funcionais Overview, Operations, Trading, Finance e Inventory.
- Operations Web mostra fila operacional e encomendas reais.
- Trade-In web cria NEG-XXXXX, vincula ENC-XXXXX, adiciona TI-XXXXX e registra complemento em dinheiro.
- Financeiro separa caixa, estoque, ativos de Trade-In, contas a receber e lucro projetado das negociações.
- Ledger financeiro visível no navegador.
- Discord e Web continuam usando a mesma base.

## Teste recomendado
1. Copie o `.env` da build validada.
2. Execute `INICIAR.bat`.
3. Abra Trading e crie primeiro uma negociação fictícia.
4. Vincule encomendas existentes, adicione uma skin fictícia e um pagamento pequeno.
5. Confira Finance e Operations.
6. Só depois cadastre a negociação real.

> O financeiro desta versão é operacional/gerencial. A V3.4 Production Hardening fará PostgreSQL definitivo, migrations formais, autenticação web/RBAC e endurecimento transacional.
