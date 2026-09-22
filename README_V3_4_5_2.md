# Clutch OS V3.4.5.2 — Frontend Identity Bootstrap

- Control Center opens through a unique uncached bootstrap route.
- Legacy service workers and browser Cache Storage are removed before the dashboard loads.
- Guild namespace is never restored from browser storage.
- A single `identityReady` promise resolves `/api/v1/identity` before any guild-scoped request.
- Backend Identity Lock remains active and returns 409 for non-canonical namespaces.
- Canonical Discord guild: `1549553223470416022`.
