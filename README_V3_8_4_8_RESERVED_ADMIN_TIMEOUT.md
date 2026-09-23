# Clutch OS V3.8.4.8 — Reserved Admin + Timeout Diagnostics

- Mantém EDITAR SKIN e INSPECIONAR visíveis em anúncios RESERVED.
- Remove apenas COMPRAR enquanto a skin estiver reservada.
- Mantém EXCLUIR SKIN no menu administrativo, com cancelamento seguro de reserva não paga.
- Adiciona diagnóstico explícito `[RESERVATION SCAN]` para cada skin RESERVED.
- Recovery legado usa deadlines disponíveis de skin/venda e não deixa estados antigos não protegidos travarem estoque indefinidamente.
- PAYMENT_CONFIRMED / TRADE_SENT / COMPLETED permanecem protegidos.
