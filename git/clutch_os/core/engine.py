import json, uuid
from decimal import Decimal
from sqlalchemy import select, func
from clutch_bot.db import Session
from clutch_bot.models import Skin, Sale, Ledger
from .models_ext import DomainEvent, RiskRule, JournalEntry, JournalLine

def D(x): return Decimal(str(x or 0)).quantize(Decimal('0.01'))
def emit(guild,event_type,entity_type,entity_id,payload=None,key=None):
    key=key or f'{event_type}:{entity_type}:{entity_id}:{uuid.uuid4().hex}'
    with Session.begin() as s:
        if s.scalar(select(DomainEvent).where(DomainEvent.event_key==key)): return key
        s.add(DomainEvent(guild_id=guild,event_key=key,event_type=event_type,entity_type=entity_type,entity_id=entity_id,payload=json.dumps(payload or {},ensure_ascii=False)))
    return key

def rule(guild,key,default):
    with Session() as s:
        r=s.get(RiskRule,(guild,key)); return Decimal(r.value) if r else Decimal(str(default))

def wallet(guild):
    with Session() as s:
        ledger=D(s.scalar(select(func.coalesce(func.sum(Ledger.amount),0)).where(Ledger.guild_id==guild)))
        inventory=D(s.scalar(select(func.coalesce(func.sum(Skin.cost+Skin.acquisition_fees),0)).where(Skin.guild_id==guild,Skin.status.in_(['AVAILABLE','RESERVED','TRADE_LOCK']))))
        potential=D(s.scalar(select(func.coalesce(func.sum(Skin.price-(Skin.cost+Skin.acquisition_fees)),0)).where(Skin.guild_id==guild,Skin.status.in_(['AVAILABLE','RESERVED']))))
        reserved=D(s.scalar(select(func.coalesce(func.sum(Skin.cost+Skin.acquisition_fees),0)).where(Skin.guild_id==guild,Skin.status=='RESERVED')))
        return {'cash':ledger,'inventory':inventory,'reserved':reserved,'potential_profit':potential}

def analyze_purchase(guild,cost,quick_sell,fees=0,liquidity='MEDIUM'):
    cost=D(cost); quick=D(quick_sell); fees=D(fees); landed=cost+fees; profit=quick-landed; roi=(profit/landed*100) if landed else Decimal(0); w=wallet(guild)
    min_profit=rule(guild,'min_profit',20); min_roi=rule(guild,'min_roi',8); max_cash_pct=rule(guild,'max_cash_pct_per_skin',20)
    impact=(landed/w['cash']*100) if w['cash']>0 else Decimal(100)
    checks={'profit':profit>=min_profit,'roi':roi>=min_roi,'liquidity':liquidity.upper() not in ('LOW','BAIXA'),'cash_concentration':impact<=max_cash_pct}
    return {'landed_cost':landed,'quick_sell':quick,'profit':profit,'roi':roi,'cash_impact_pct':impact,'liquidity':liquidity,'checks':checks,'meets_all':all(checks.values())}

def post_journal(guild,event_key,memo,lines):
    deb=sum(D(x.get('debit')) for x in lines); cred=sum(D(x.get('credit')) for x in lines)
    if deb!=cred: raise ValueError(f'Lançamento não balanceado: débito {deb} != crédito {cred}')
    with Session.begin() as s:
        old=s.scalar(select(JournalEntry).where(JournalEntry.event_key==event_key))
        if old:return old.code
        e=JournalEntry(guild_id=guild,code='PENDING',event_key=event_key,memo=memo);s.add(e);s.flush();e.code=f'JE-{e.id:06d}'
        for x in lines:s.add(JournalLine(entry_id=e.id,account_code=x['account'],debit=D(x.get('debit')),credit=D(x.get('credit')),skin_id=x.get('skin_id')))
        return e.code
