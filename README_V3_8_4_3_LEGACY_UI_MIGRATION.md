# Clutch OS V3.8.4.3 — Legacy UI Migration

- Buylist pausada mantém o painel canônico sem botão de venda.
- Painéis legados do bot com `v2:buy:new` são removidos uma única vez enquanto a Buylist está pausada.
- Anúncios `AVAILABLE` antigos recebem `✏️ EDITAR SKIN` na mesma mensagem, preservando SK, imagem, preço, float, pattern, inspect, custos e histórico.
- Migração do catálogo é idempotente e grava marcador no PostgreSQL após sucesso; não volta a fazer PATCH em massa nos boots seguintes.
- Nenhuma permissão de canal é alterada. Nenhum dado de negócio é apagado.
