# Clutch OS V3.3.2 — Control Center Bridge

## Mudanças
- `INICIAR.bat` agora sobe **API/Control Center + Discord Bot**.
- O navegador abre automaticamente em `http://127.0.0.1:8000/`.
- `/health` confirma o serviço web.
- O Control Center detecta automaticamente o guild quando existe apenas um servidor configurado no banco.
- Mantém o Proposal Workflow da V3.3.1.

## Teste
1. Copie seu `.env` para esta pasta.
2. Execute `INICIAR.bat`.
3. Aguarde `[CLUTCH WEB] Control Center iniciado`.
4. O navegador deve abrir sozinho.
5. Se houver mais de um guild, use `http://127.0.0.1:8000/?guild=SEU_GUILD_ID`.

## Observação sobre Unknown Interaction
A V3.3.1 já usa `defer()` nos callbacks operacionais demorados e `followup` após processamento. O traceback mostrado no teste anterior apontava para a pasta V3.3 (`Clutch_OS_V3_3_Trading_Operations`), não para esta build V3.3.1/3.3.2.
