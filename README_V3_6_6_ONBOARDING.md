# Clutch OS V3.6.6 — Onboarding Gate

- Novo painel persistente **ENTRAR PARA O CLUB**.
- `/configurar-onboarding canal cargo` define o canal de boas-vindas e o cargo Cliente.
- `/publicar-onboarding` recria/atualiza o painel.
- O botão atribui o cargo configurado somente após o clique.
- Corrigida a identificação visual do Control Center para V3.6.6.

## IMPORTANTE — permissões do Discord
O bot não consegue esconder canais por conta própria antes do clique. Configure as permissões do servidor assim:
1. `@everyone`: permitir somente os canais de entrada (boas-vindas, como-funciona, segurança e, se desejar, anúncios).
2. Cargo `Cliente`: permitir Loja, Comunidade e demais canais públicos.
3. Cargo `Clutch Bot`: acima de `Cliente` e com **Gerenciar Cargos**.
4. Desative qualquer Auto Role/integração que entregue `Cliente` automaticamente ao entrar.

Depois execute `/configurar-onboarding` apontando para `#boas-vindas` e o cargo `Cliente`.
