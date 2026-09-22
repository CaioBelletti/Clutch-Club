# Clutch OS V3.3.1 — Proposal Workflow

## Mudanças principais
- Staff não pode mais marcar `CLIENTE ACEITOU`.
- `OPEN -> SEARCHING` continua pelo Operations Center.
- Em `SEARCHING`, a ação abre formulário **Registrar skin encontrada**.
- Formulário exige custo, preço ao cliente e fornecedor; aceita float e listing/inspect.
- O card operacional mostra custo, preço, float encontrado, fornecedor e links.
- Em `FOUND`, a ação abre **Enviar proposta**, com validade configurável.
- O cliente recebe a proposta por DM com **ACEITAR PROPOSTA** / **RECUSAR**.
- Somente o cliente pode gerar `CUSTOMER_ACCEPTED`.
- Recusa devolve a encomenda para `SEARCHING`.
- Callbacks críticos reconhecem a interação imediatamente para reduzir "bot não respondeu a tempo".
- Trade Lock ativo impede avanço para READY até a data passar.
- Migração aditiva preserva bancos V3.2/V3.3 e adiciona campos de proposta.

## Teste recomendado
1. `/diagnostico`.
2. Criar encomenda fictícia.
3. `ASSUMIR`.
4. `AÇÃO / PRÓXIMA ETAPA` -> PROCURANDO.
5. Clique novamente -> preencher skin encontrada.
6. Clique novamente -> enviar proposta.
7. Confirmar que Staff fica bloqueado em `PROPOSTA AO CLIENTE`.
8. Cliente aceita pela DM.
9. Confirmar mudança para `CLIENTE ACEITOU` no Operations Center.

Não use dados financeiros reais até concluir este teste.
