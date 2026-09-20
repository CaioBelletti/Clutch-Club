# Clutch OS V3.1.1 — Discord Bootstrap Hotfix

Correção de robustez para o bootstrap do Discord.

## Corrigido
- Um canal sem permissão não derruba mais o `on_ready`.
- Diagnóstico individual de `buylist`, `catalog`, `interest` e `order` no console.
- Verificação prévia de `view_channel`, `send_messages`, `embed_links` e `read_message_history`.
- `/publicar-paineis` agora informa quais painéis falharam e o motivo.
- Novo `/diagnostico` verifica banco, canais e permissões dos 7 canais operacionais.
- Views persistentes e sync são registrados apenas uma vez por processo, evitando trabalho duplicado em reconnects.
- Painel reconfigurado para outro canal é recriado corretamente no novo destino.

## Sobre Message Content Intent
O warning do discord.py não é a causa do erro 403. Os fluxos atuais do Clutch OS usam slash commands, botões e modais e não dependem da leitura do conteúdo de mensagens comuns.
