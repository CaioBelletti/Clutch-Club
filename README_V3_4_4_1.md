# Clutch OS V3.4.4.1 — Discord Bootstrap Shield

Hotfix sobre V3.4.4. O sync de slash commands não pode mais interromper `on_ready`.

- usa `bot.get_guild(GUILD_ID)` em vez de `discord.Object` para sync por guild;
- registra todas as guilds realmente conectadas ao bot;
- trata Forbidden, NotFound e HTTPException;
- continua persistent views, painéis e Operations mesmo se o sync falhar;
- não altera o recovery/schema migration validado na V3.4.4.

No primeiro boot, confira `[DISCORD] Guilds conectadas:`. Esse valor é a evidência autoritativa para confirmar a identidade Discord antes de qualquer nova migração de guild.
