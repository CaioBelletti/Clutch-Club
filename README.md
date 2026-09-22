# Clutch Bot V2.0 Production

Bot operacional da Clutch Club para Discord, com clientes usando botões/formulários e staff usando comandos administrativos.

## Incluído
- Buylist: solicitação, proposta, contraproposta, aceite do vendedor, recebimento, PIX e entrada automática no estoque.
- Vendas: reserva com expiração, pagamento, trade, conclusão/cancelamento e ledger.
- Catálogo: cards de skins, código único SK-XXXXX, inspect e reserva pelo cliente.
- Financeiro: aquisição, taxas, venda, taxas de venda, capital em estoque, caixa líquido, receita e resultado acumulado.
- Railway/PostgreSQL: SQLAlchemy + psycopg, Dockerfile, Procfile e railway.json.
- Configuração de canais dentro do Discord com /configurar-canal.
- Lista de interesse com match automático por nome/exterior/orçamento/float.
- Encomendas ENC-XXXXX.
- Coleção pessoal com retirada e devolução sem registrar venda.
- Feedback/reputação.
- Análise de compra baseada nas regras: lucro >= R$20, ROI >= 8% e liquidez não baixa.
- Control Center /painel e auditoria no banco.
- Painéis persistentes: Buylist, Catálogo, Interesse, Encomendas e Feedback.

## Primeira execução local
1. Instale Python 3.11+.
2. Rode `INSTALAR.bat`.
3. Copie `.env.example` para `.env` e informe `DISCORD_TOKEN` e `GUILD_ID`.
4. Rode `INICIAR.bat`.
5. No Discord, use `/configurar-canal` para catalog, buylist, interest, order e feedback.
6. Use `/publicar-paineis` uma vez. Depois os clientes não precisam de slash commands.

## Fluxo Buylist
PENDING -> PROPOSED -> ACCEPTED -> RECEIVED -> PAID -> COMPLETED/estoque.
O vendedor pode gerar COUNTERED; o staff responde com nova proposta. REJECTED encerra.

## Fluxo Venda
AVAILABLE -> RESERVED -> PAYMENT_CONFIRMED -> TRADE_SENT -> COMPLETED/SOLD.
Reserva expira automaticamente e volta a AVAILABLE. CANCELLED também libera a skin.

## Railway
Crie um serviço PostgreSQL e o serviço do bot. Configure `DISCORD_TOKEN`, `GUILD_ID` e `DATABASE_URL` com a URL do PostgreSQL. O processo de produção é `python -m clutch_bot.main`.

## Observação sobre migrations
A V2 inclui uma migration SQL inicial em `migrations/001_v2_schema.sql` para provisionamento/auditoria. Em banco vazio, o bot também cria as tabelas automaticamente via SQLAlchemy. Para migração de dados de versões antigas, use o script `migrate_legacy.py` após backup.
