# Clutch Bot V2.1 — Public Flow Fix

Correção focada na experiência pública do servidor.

## Alterações
- Buylist pública mostra somente `QUERO VENDER UMA SKIN`.
- Aceite e contraproposta passam a ser enviados ao vendedor junto da proposta, por DM.
- Painel permanente de Lista de Interesse.
- Painel permanente de Encomendas.
- Canal de Avaliações não recebe painel público; só publica avaliações vinculadas a vendas concluídas.
- Ao concluir uma venda, o comprador recebe convite privado para avaliação.
- Canal `news`/Novidades recebe feed quando uma skin entra no estoque.
- Canal `sold`/Skins vendidas recebe feed ao concluir uma venda.
- `/configurar-canal` agora oferece Catálogo, Buylist, Lista de interesse, Encomendas, Avaliações verificadas, Novidades e Skins vendidas.
- `/publicar-paineis` publica somente os quatro painéis interativos públicos: catálogo, buylist, interesse e encomendas.
- Views de proposta e avaliação são persistentes após reinício do bot.

## Atualização
Pode usar o mesmo `.env` e banco da V2.0. Esta versão não altera o schema do banco.

1. Pare a V2.0.
2. Copie seu `.env` e, se estiver usando SQLite local, o arquivo de banco para esta pasta conforme sua configuração atual.
3. Inicie a V2.1.
4. Configure também `news`, `sold` e `feedback` com `/configurar-canal`.
5. Rode `/publicar-paineis` uma vez. Depois, com `AUTO_PUBLISH=true`, o bot mantém os painéis configurados ao reiniciar.

O canal de avaliações deve permanecer sem botão público. As avaliações aparecem nele somente após uma venda verificada e concluída.
