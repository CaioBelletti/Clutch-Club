# Clutch OS V3.6.9 — Access State Hotfix

- `/configurar-onboarding` agora verifica o estado efetivo antes de escrever permissões.
- Canais já corretos não recebem `set_permissions`, evitando falsos `Forbidden`.
- Após qualquer correção, o acesso é relido e validado.
- Erros reais informam canal e operação que recebeu 403/HTTP.
- `/diagnostico` continua mostrando o estado efetivo do cargo Cliente.
- Boot registra um resumo `[ACCESS]` da matriz de acesso.
- Banco canônico e dados persistentes não são alterados por esta atualização.
