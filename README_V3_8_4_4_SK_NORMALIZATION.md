# Clutch OS V3.8.4.4 — SK Normalization

Migração única confirmada pelo operador:

- SK-00002 → SK-00001
- SK-00003 → SK-00002
- SK-00004 → SK-00003
- SK-00005 → SK-00004
- SK-00007 → SK-00005
- SK-00008 → SK-00006
- SK-00009 → SK-00007

Resíduos de teste SK-00001, SK-00006 e SK-00010 são preservados como TEST-SK-xxxxx com status TEST_ARCHIVED. Nenhum registro histórico é apagado.

Relacionamentos internos continuam usando `skins.id`, portanto sales, ledger, buylist e trade-in permanecem ligados à mesma skin. Os anúncios válidos mantêm o mesmo `message_id` e são atualizados no Discord.

Após a migração, novos cadastros usam sequência pública independente do ID interno; o próximo código será SK-00008.
