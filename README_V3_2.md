# Clutch OS V3.3 — Operations Center

## O que mudou
- Nova fila `operations_queue`: nenhuma solicitação comercial precisa ficar somente no banco.
- Encomendas criam pendência operacional e notificam o canal de staff configurado.
- Buylist, contraproposta e reserva/venda também entram na fila.
- Canal `Operations Center` configurável via `/configurar-canal`.
- Cards administrativos com ASSUMIR, CONCLUIR e CANCELAR.
- `/operacoes` lista pendências.
- `/republicar-operacoes` recupera pendências antigas sem mensagem de staff.
- API `/api/v1/operations/{guild_id}` e contador de fila no Control Center Web.
- V3.1.1 de diagnóstico/permissões preservada.

## Configuração inicial
1. Crie um canal privado de staff, sugestão: `📟・operations-center` dentro de ATENDIMENTOS.
2. `/configurar-canal` → `Operations Center` → selecione o canal.
3. Garanta ao bot Ver canal, Enviar mensagens, Incorporar links e Ler histórico.
4. Rode `/diagnostico`.
5. Rode `/republicar-operacoes` para publicar solicitações que já estavam no banco.

## Observação
Os botões do Operations Center controlam a fila administrativa. Os estados de negócio (ex.: encomenda encontrada/adquirida/entregue) continuam separados e serão evoluídos sem misturar auditoria com simples ocultação de pendência.
