# CLUTCH OS V3.7.2 — Button Workflow

Hotfix de lançamento focada em eliminar comandos slash do fluxo operacional normal de Buylist e Venda.

## Buylist
- CLIENTE ACEITOU → botão **CONFIRMAR SKIN RECEBIDA**.
- SKIN RECEBIDA → botão **CONFIRMAR PIX PAGO**.
- PAGAMENTO REGISTRADO → botão **ADICIONAR AO ESTOQUE**.
- A entrada em estoque abre modal para preço de venda e taxas e publica a skin no catálogo.
- `/buylist-etapa` foi preservado como fallback administrativo.

## Venda
- PAGAMENTO PENDENTE → botão **CONFIRMAR PAGAMENTO**.
- PAGAMENTO CONFIRMADO → botão **CONFIRMAR TRADE ENVIADA**.
- TRADE ENVIADA → botão **CONCLUIR VENDA**.
- Conclusão abre modal opcional de taxas, fecha financeiro/estoque, publica venda e convida o cliente a avaliar.
- `/venda-etapa` foi preservado como fallback administrativo.

## Segurança operacional
- As transições continuam validadas no banco; um botão antigo não consegue pular etapas.
- O mesmo BL/VD e o mesmo card operacional são atualizados; não é criado novo ticket ao avançar.
- Fluxo de encomenda (ENC) e avaliações verificadas foram preservados.
- Banco canônico externo `..\\Clutch_OS_DATA\\clutch_v2.db` não faz parte deste pacote.

## Interface
- Identificação visual/cache do Control Center sincronizada para V3.7.2.
