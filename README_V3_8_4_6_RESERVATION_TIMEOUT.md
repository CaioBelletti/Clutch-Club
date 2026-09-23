# Clutch OS V3.8.4.6 — Reservation Timeout

- Reserva direta continua com 30 minutos (RESERVATION_MINUTES).
- Venda em `RESERVED` vencida volta automaticamente para `AVAILABLE`.
- A operação VD é marcada `CANCELLED` e o anúncio é atualizado.
- O ticket é arquivado e preservado como histórico.
- Nenhum lançamento financeiro é criado pelo timeout.
- `PAYMENT_CONFIRMED` e etapas posteriores nunca expiram automaticamente.
- Reservas vencidas durante downtime/redeploy são recuperadas no boot.
- Housekeeping roda a cada 1 minuto.
