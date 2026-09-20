# Clutch OS V3.8.0 — Tickets + Welcome

Escopo cirúrgico sobre a base V3.7.6 validada em produção.

- Mantém PostgreSQL/Railway, Control Center, catálogo, estoque, financeiro e CS2 Inspect.
- Mensagem individual automática no #boas-vindas via on_member_join.
- Ticket privado automático para VD (venda), ENC (encomenda) e BL (buylist).
- Ticket e Operations Center usam a mesma operação/código; não cria negociação duplicada.
- Atualizações de status também aparecem no ticket.
- Ticket é arquivado ao encerrar, preservando histórico.
- Avaliação de venda contextual: o cliente não precisa digitar o código VD.

## Discord Developer Portal
Ative **Server Members Intent** para o bot antes do deploy. Sem esse intent o Discord não entrega on_member_join.
