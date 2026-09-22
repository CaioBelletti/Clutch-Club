# Clutch OS V3.4.3.1 — Forensics + Guild Repair

Correção focada em duas falhas observadas na V3.4.2: discovery histórico incompleto e Order recuperada fora do guild canônico.

- varre arquivos pela assinatura SQLite, independentemente do nome/extensão;
- imprime roots e todos os bancos históricos encontrados;
- inventaria guild_id por tabela;
- consolida fontes válidas antes de API/Bot;
- determina guild canônica por GUILD_ID ou configuração/painéis;
- repara somente Orders/Operations em guild órfã de configuração;
- reconcilia Customer + Order + Operation;
- valida ENC históricas antes do commit;
- backup antes da promoção.
