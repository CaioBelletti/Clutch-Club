# Clutch OS V3.3.7 — Bug Shield

Hotfix preventiva sobre a V3.3.6.

- Trading usa `CL-XXXXX` como identidade canônica; não depende do Discord ID vindo do navegador.
- Encomendas do seletor são carregadas por endpoint do cliente.
- NEG exige pelo menos uma encomenda, valida propriedade e bloqueia reutilização em NEG ativa.
- Endpoint auditável para relink de encomenda legada ao CRM.
- Production Gate ampliado: TI→SK, SK única, SK somente após aceite, CRM duplicado, CRM↔Orders, NEG↔Cliente↔Orders, encomenda em uma única NEG ativa, pagamentos e crédito.
- Importação CRM permanece idempotente pela constraint guild+Discord.

Não use dados financeiros reais até o Production Gate estar PRONTO e o teste funcional passar.
