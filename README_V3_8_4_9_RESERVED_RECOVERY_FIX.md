# Clutch OS V3.8.4.9 — Reserved Recovery Fix

- Reservation scanner always logs the number of RESERVED skins, including zero.
- Startup reconciliation fetches active catalog messages and PATCHes only stale/mismatched cards.
- RESERVED cards keep EDITAR SKIN + INSPECIONAR and do not show COMPRAR.
- AVAILABLE cards keep EDITAR SKIN + COMPRAR + INSPECIONAR.
- Existing Skin Delete flow is preserved.
- No catalog-wide unconditional PATCH was reintroduced.
