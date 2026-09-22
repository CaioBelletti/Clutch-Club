# Clutch OS V3.6.4 — Trade Lock UX Hotfix

## Correções
- O botão AÇÃO / PRÓXIMA ETAPA em uma encomenda ADQUIRIDA agora pergunta se existe Trade Lock.
- `TEM TRADE LOCK` abre um formulário para informar a data/hora real.
- `SEM LOCK → READY` avança diretamente para PRONTA PARA ENTREGA.
- Datas de Trade Lock são interpretadas no horário de São Paulo e persistidas em UTC.
- Data sem horário (`DD/MM/AAAA`) significa fim daquele dia (23:59:59), evitando lock expirado à meia-noite.
- Datas de Trade Lock no passado são rejeitadas.
- Ao vencer o lock, AÇÃO / PRÓXIMA ETAPA avança TRADE LOCK → READY.
- Corrigida comparação de datetime SQLite naive/UTC aware.
- `/encomenda-etapa` continua disponível, mas READY deve ser escolhido em `etapa`; `trade_lock_ate` é exclusivo para TRADE LOCK.
- Corrigido import de Audit usado pelo reset de encomendas de teste.

## Teste recomendado
1. Use uma encomenda em ADQUIRIDA.
2. Clique AÇÃO / PRÓXIMA ETAPA.
3. Teste SEM LOCK → READY; depois READY → ENTREGUE.
4. Em outra encomenda ADQUIRIDA, escolha TEM TRADE LOCK e informe uma data futura.
5. Confirme que o card e a DM exibem a data corretamente.
