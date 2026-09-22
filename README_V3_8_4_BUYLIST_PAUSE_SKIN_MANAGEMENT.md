# Clutch OS V3.8.4 — Buylist Pause & Skin Management

- `BUYLIST_ENABLED=false` por padrão. Buylist fica oculta para Cliente, histórico preservado.
- Para reativar: Railway Variables -> `BUYLIST_ENABLED=true` -> redeploy.
- Onboarding rápido não oferece VENDER enquanto a buylist estiver pausada.
- Anúncios de skin agora possuem `✏️ EDITAR SKIN` (Staff/Fundador).
- Edição por botões: Dados, Valores e Imagem/Inspect. Mantém a mesma SK e o mesmo message_id.
- Skin RESERVED bloqueia edição de dados/valores críticos.
- Sincronização em massa de anúncios no boot removida para evitar rate limit 429.
- Control Center exibe estado da Buylist.
- Sem reset/migração destrutiva de banco.
