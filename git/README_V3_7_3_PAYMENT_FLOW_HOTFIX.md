# Clutch OS V3.7.3 — Payment Flow Hotfix

- Encomenda aceita agora exige escolha do cliente entre PIX e cartão.
- PIX envia chave configurada, valor e botão de aviso de pagamento.
- Cartão notifica Operations; staff insere link oficial pelo botão AÇÃO / PRÓXIMA ETAPA.
- Staff confirma pagamento por botão; `/encomenda-etapa` permanece fallback administrativo.
- A aquisição só avança depois de pagamento confirmado.
- Configuração: `/configurar-pagamento pix_chave:<chave> favorecido:<nome>`.
