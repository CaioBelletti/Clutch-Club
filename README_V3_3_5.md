# Clutch OS V3.3.5 — Trade-In Lifecycle + Finance

Evolução da V3.3.4 validada.

## Trade-In lifecycle
- TI-XXXXX: EXPECTED -> RECEIVED -> INSPECTED -> ACCEPTED -> SK-XXXXX.
- REJECTED disponível antes da aceitação.
- SK só nasce quando o ativo é aceito no estoque.
- Proteção contra dupla criação de SK por TI.

## NEG lifecycle
Status operacional é calculado pelo estado real:
- OPEN
- FINANCIALLY_SETTLED
- AWAITING_ASSETS
- ASSETS_RECEIVED
- COMPLETED
- CANCELLED

Pagamento do caixa não conclui sozinho uma negociação com Trade-In pendente.

## Financeiro
- Caixa e Trade-In separados.
- Trade-In a receber separado de Trade-In no estoque.
- Crédito EXPECTED não é estoque.
- Lucro projetado fica "Aguardando CMV" enquanto os custos das encomendas vinculadas não estiverem conhecidos.

## Proteções
- Bloqueia crédito de TI acima do crédito negociado.
- Bloqueia pagamento acima do saldo em dinheiro.
- Bloqueia transições de estado inválidas.
- Bloqueia cancelamento depois de pagamento confirmado ou ativo aceito.

## UX
- Cliente passa a ser selecionado pelo CRM quando houver cadastro.
- Encomendas são selecionadas em lista, em vez de digitação manual de códigos.
- Ações contextuais por TI no Control Center.

## Teste automatizado executado
Cenário: venda 100 / trade-in 60 / PIX 40 / dois TIs 35+25 / encomenda com custo 70.
Resultado: AWAITING_ASSETS após liquidação financeira; COMPLETED somente após aceitar os dois ativos; caixa 40; trade-in em estoque 60; 2 SKs criadas; excesso de crédito e pagamento retornando HTTP 409.
