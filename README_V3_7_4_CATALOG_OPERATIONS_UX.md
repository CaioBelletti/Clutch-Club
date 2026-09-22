# Clutch OS V3.7.4 — Catalog & Operations UX Hotfix

## Alterações
- `/cadastrar-skin` agora aceita `imagem` (anexo do Discord). O anexo tem prioridade sobre `imagem_url`.
- A imagem fica vinculada ao registro `SK-xxxxx` e é reutilizada no embed do catálogo.
- Pagamento PIX mostra somente `CONFIRMAR PAGAMENTO`.
- `ENVIAR LINK DO CARTÃO` aparece somente quando o cliente escolheu CARTÃO.
- Ao confirmar o pagamento de uma encomenda, o card auxiliar de pagamento é removido/desativado para reduzir poluição visual.
- Banco externo `..\Clutch_OS_DATA\clutch_v2.db` e dados existentes permanecem preservados.

## Teste recomendado
1. Cadastrar uma skin anexando um print em `imagem`.
2. Confirmar que o anúncio do catálogo mostra a imagem.
3. Criar ENC e escolher PIX: deve aparecer apenas `CONFIRMAR PAGAMENTO` para a equipe.
4. Confirmar PIX: o card auxiliar deve desaparecer.
5. Criar outra ENC e escolher CARTÃO: deve aparecer também `ENVIAR LINK DO CARTÃO`.
