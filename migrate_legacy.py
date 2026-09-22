"""Assistente conservador de migração.
Use somente com backup. A V2 preserva a V1.9; este script valida conexão e informa contagens.
Migrações automáticas destrutivas não são executadas silenciosamente.
"""
from clutch_bot.db import init_db,Session
from clutch_bot.models import Skin,Buylist
from sqlalchemy import select,func
init_db()
with Session() as s:
    print('Skins:',s.scalar(select(func.count()).select_from(Skin)))
    print('Buylists:',s.scalar(select(func.count()).select_from(Buylist)))
print('Banco V2 acessível. Faça a importação do legado somente após backup e validação dos campos.')
