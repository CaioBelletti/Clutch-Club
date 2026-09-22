# Clutch OS V3.3.3 — Dashboard Data Fix

Hotfix sobre a V3.3.2.

## Correções
- Corrige o JOIN Sale -> Skin do lucro realizado para SQLAlchemy 2.x usando `select_from(Sale)`.
- KPIs do dashboard são isolados: falha em um indicador não derruba todo o endpoint.
- `/health` informa a base usada pelo Core/API.
- API e Discord imprimem a base resolvida no startup para conferir a fonte de verdade.
- `/favicon.ico` e `/sw.js` deixam de gerar 404 no log.
- Versão da API atualizada para 3.3.3.

## Teste
1. Copie seu `.env` para esta pasta.
2. Execute `INICIAR.bat`.
3. Confira se `API/Core DB` e `Discord Bot DB` exibem o mesmo banco.
4. Abra http://127.0.0.1:8000/
5. Confirme que `/api/v1/dashboard/<guild_id>` responde 200.
