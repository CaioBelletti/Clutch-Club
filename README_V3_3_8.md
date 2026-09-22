# Clutch OS V3.3.8 — Data Reconciliation & Self-Healing

- `orders.customer_id` passa a ser o vínculo canônico CRM ↔ Encomenda.
- `user_id` legado é preservado para auditoria; não é sobrescrito durante reconciliação.
- Nova tela Reconciliation mostra total, vinculadas, sem CRM e vínculos quebrados.
- Vinculação manual exige confirmação e gera Audit Log.
- Production Gate reprova qualquer encomenda sem CRM canônico ou com customer_id inválido.
- Novas encomendas do Discord criam/reutilizam Customer e gravam customer_id automaticamente.
- Trading só aceita ENC cujo customer_id corresponda ao CL selecionado.
- Nenhuma reconciliação automática ambígua: casos legados precisam de seleção explícita do cliente.
