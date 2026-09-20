# Clutch OS V3.4.1 — Safe Migration

Migração transacional para o banco canônico compartilhado.

- fontes legadas abertas em read-only;
- staging database antes do banco definitivo;
- normalização de campos obrigatórios legados (incluindo created_at/updated_at);
- merge por chaves naturais sem sobrescrever registros canônicos;
- foreign keys validadas após a cópia;
- backup automático do banco canônico anterior;
- promoção atômica somente após validação;
- relatório em `..\Clutch_OS_DATA\migration_report_v3_4_1.json`;
- API e Discord só iniciam depois do término da migração.

Se a validação falhar, a staging é descartada e o banco canônico anterior é preservado.
