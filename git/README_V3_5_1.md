# Clutch OS V3.6.2 — Canonical Runtime

Correção estrutural final do namespace local. O Core é a autoridade do namespace e canonicaliza clientes legados antes do roteamento, impedindo que uma aba antiga consulte dados de outra guild.

Também repara duplicatas históricas de Operations por Order sem apagar auditoria: mantém uma operação ativa e inativa duplicatas antigas.

Critérios: Discord/Core/Web no namespace 1549553223470416022; dashboard não mascara erros; 1 Order -> 1 Operation ativa; dados históricos preservados.
