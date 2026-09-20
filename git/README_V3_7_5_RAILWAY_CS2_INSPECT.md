# Clutch OS V3.7.5 — Railway + CS2 Inspect

## Novidades
- Botão **🎮 INSPECIONAR NO CS2** nos anúncios que possuem `inspect_link`.
- O botão usa uma URL HTTPS pública (`/inspect/SK-XXXXX`) compatível com Discord.
- A página pública tenta abrir automaticamente o URI `steam://run/730//+csgo_econ_action_preview...` e também oferece botão manual.
- `/cadastrar-skin` mantém `imagem`, `imagem_url` e `inspect_link`.
- Railway/PostgreSQL: `run_all.py` não executa mais o recovery SQLite quando `DATABASE_URL` é PostgreSQL.
- Suporte a `PUBLIC_BASE_URL`; se omitido, usa `RAILWAY_PUBLIC_DOMAIN`.

## Railway
Configure pelo menos: `DISCORD_TOKEN`, `GUILD_ID`, `DATABASE_URL` e `ADMIN_API_KEY`.
Opcional/recomendado: `PUBLIC_BASE_URL=https://SEU-DOMINIO.up.railway.app`.
O Railway fornece `PORT`; não fixe uma porta pública manualmente.

## Fluxo Inspect
Discord → botão INSPECIONAR NO CS2 → HTTPS do Clutch OS → Chrome → confirmação Abrir Steam → Steam/CS2 → inspect.

## Segurança
A rota só aceita inspect URIs que começam com `steam://run/730//+csgo_econ_action_preview`. Outros protocolos são rejeitados.
