# Clutch OS V3.8.4.7 — Reservation Recovery + Skin Delete

- Reservation timeout scans RESERVED skins, including legacy/orphan reservations.
- PAYMENT_CONFIRMED / TRADE_SENT / COMPLETED are never auto-released.
- Expired reservations return the skin to AVAILABLE and close the abandoned ticket without ledger entries.
- Staff/Fundador can delete an AVAILABLE/RESERVED skin from the edit menu with confirmation.
- Delete archives the DB row as DEL-xxxxx, preserves historical relations, removes the Discord catalog message and releases the public SK number.
- New SK allocation uses the lowest free SK number, so deleting test SK-00008 makes the next real skin SK-00008.
