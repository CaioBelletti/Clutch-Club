# Clutch Bot V1.9 — Core Production

Nova fundação modular, separada da V1.8. **Não substitua sua V1.8 em produção sem testar.**

## O que entrou
- SQLAlchemy com SQLite local e PostgreSQL no Railway via `DATABASE_URL`.
- IDs únicos `SK-00001` e ciclo de vida do mesmo registro.
- Ledger financeiro para aquisição/venda.
- Retirada pessoal e devolução preservando custo histórico.
- Auditoria.
- Painéis permanentes de Buylist e Lista de Interesse, sem slash command para clientes.
- Validação de float.
- Match automático básico da lista de interesse ao cadastrar estoque.
- Dashboard com capital, venda potencial, receita, CMV e lucro bruto.
- Dockerfile + Railway.
- Estrutura multi-guild no banco (`guild_id`).

## Rodar local
1. Copie `.env.example` para `.env`.
2. Preencha token e IDs.
3. Execute `INSTALAR.bat`.
4. Execute `INICIAR.bat`.

## Railway/PostgreSQL
Crie um PostgreSQL no projeto e defina `DATABASE_URL=${{Postgres.DATABASE_URL}}`, além do token e IDs. O driver psycopg já está incluído.

## Importante
A V1.9 usa um esquema novo. O banco V1.8 não deve ser apontado diretamente para ela. Faça testes em servidor/canais de teste antes de migrar dados reais.

## Próxima etapa funcional
O core já está pronto para receber a V1.9.1: ticket privado completo de Buylist, proposta/contraoferta com aceite do vendedor, reserva/checkout, catálogo navegável, encomendas e feedback no novo banco.
