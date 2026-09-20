# Clutch OS V3.1 — Premium Control Center

Esta versão substitui a página web básica da V3.0 por um Control Center responsivo inspirado na referência visual enviada: dark premium, cards arredondados, contraste alto e acento neon.

## O que já é real
- Dashboard consome dados do banco pelo Core/API.
- Caixa, capital em estoque, reservado, venda potencial, receita, lucro realizado e ROI.
- Contadores de estoque, Buylist, vendas, encomendas, clientes e reputação.
- Tabela de skins reais com busca instantânea.
- Feed de auditoria/atividade.
- Layout desktop e mobile.
- API protegida por `ADMIN_API_KEY` quando configurada.

## Abrir o painel
Inicie o projeto normalmente e acesse:

`http://127.0.0.1:8000/?guild=SEU_GUILD_ID`

Se `ADMIN_API_KEY` estiver configurada, durante desenvolvimento também é possível passar `&key=SUA_CHAVE`; o navegador guarda a configuração localmente. Em produção, não exponha a chave na URL: a próxima etapa deve usar autenticação/sessão.

## Próximas telas
A navegação visual já está preparada para Inventory, Trading, Finance, Customers, Intelligence e Reports. Nesta versão, Overview é a tela funcional implementada; os demais itens ainda não fingem ser telas prontas.
