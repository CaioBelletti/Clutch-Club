# Clutch OS V3.4.5.1 — Web Identity Lock

Hotfix de identidade do Control Center.

- O Web aguarda `/api/v1/identity` antes de carregar KPIs e módulos.
- Remove namespace de guild legado de localStorage/sessionStorage no boot.
- HTML e endpoint de identidade usam `Cache-Control: no-store`.
- Backend bloqueia com HTTP 409 qualquer `/api/v1/<recurso>/<guild_id>` cujo guild_id não seja a guild canônica `1549553223470416022`.
- API, Web e Discord permanecem no namespace canônico confirmado pelo Discord.
