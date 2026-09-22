# Clutch OS V3.0 — Extreme Foundation

V3 transforma o projeto em plataforma: Discord para clientes + API/Web administrativa + PostgreSQL/SQLAlchemy + Redis opcional + eventos + financeiro preparado para partidas dobradas + RBAC + risco.

## Componentes
- `clutch_bot/`: interface Discord e fluxos comerciais herdados/evoluídos da V2.1.
- `clutch_os/api/`: FastAPI, health check e API administrativa.
- `clutch_os/core/`: eventos, carteira, risk engine e journal financeiro.
- PostgreSQL em produção via `DATABASE_URL`; SQLite continua aceito para desenvolvimento.
- Railway executa API e bot juntos via `run_all.py` nesta fase.

## Novas tabelas V3
`customers`, `accounts`, `journal_entries`, `journal_lines`, `domain_events`, `staff_roles`, `risk_rules`.

## Segurança
Defina `ADMIN_API_KEY`. Nunca versionar `.env` ou token do Discord. Para produção use PostgreSQL. Redis foi incluído como dependência para a próxima camada de locks/cache/workers; o Core não exige Redis para iniciar.

## Teste local
1. `python -m venv .venv`
2. Ative o ambiente e `pip install -r requirements.txt`
3. Copie `.env.example` para `.env` e preencha.
4. `python run_all.py`
5. Abra `http://localhost:8000/health` e `http://localhost:8000/docs`.

## Railway
Crie PostgreSQL, configure `DATABASE_URL`, `DISCORD_TOKEN`, `GUILD_ID`, `ADMIN_API_KEY` e faça deploy do repositório. O health check é `/health`.

## Critérios padrão do Risk Engine
Lucro mínimo R$20; ROI mínimo 8%; liquidez não-baixa; concentração máxima padrão 20% do caixa por skin. São regras configuráveis e servem como análise, não execução automática de compra.

## Observação
A V3 é uma fundação extrema executável, não uma alegação de que integrações externas de preço/Steam/BUFF estejam implementadas. Essas integrações exigem APIs/fontes e credenciais apropriadas. O Core foi preparado para recebê-las sem colocar regra de negócio dentro do Discord.
