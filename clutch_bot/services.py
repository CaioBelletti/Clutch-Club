from datetime import datetime,timezone,timedelta
from decimal import Decimal
from sqlalchemy import select,func
from .db import Session
from .models import Skin,Sale,Buylist,Ledger,Audit,Interest,GuildConfig,Feedback

def D(v):
    s=str(v or 0).strip().replace('R$','').replace(' ',''); s=s.replace('.','').replace(',','.') if ',' in s else s
    return Decimal(s).quantize(Decimal('0.01'))
def valid_float(v):
    try:return Decimal('0')<=Decimal(str(v).replace(',','.'))<=Decimal('1')
    except:return False
def log(s,g,a,action,etype,eid=None,detail=None):s.add(Audit(guild_id=g,actor_id=a,action=action,entity_type=etype,entity_id=eid,detail=detail))
def cfg(g,key,default=None):
    with Session() as s:r=s.get(GuildConfig,(g,key));return r.value if r else default
def set_cfg(g,key,value):
    with Session.begin() as s:s.merge(GuildConfig(guild_id=g,key=key,value=str(value)))
def create_skin(guild,name,exterior,floatv,pattern,stickers,price,cost=0,inspect=None,source='MANUAL',source_ref=None,fees=0):
    if not valid_float(floatv):raise ValueError('Float deve estar entre 0 e 1.')
    with Session.begin() as s:
        x=Skin(code='PENDING',guild_id=guild,name=name,exterior=exterior.upper(),floatv=str(floatv).replace(',','.'),pattern=pattern,stickers=stickers,price=D(price),cost=D(cost),acquisition_fees=D(fees),inspect=inspect,source=source,source_ref=source_ref);s.add(x);s.flush();x.code=f'SK-{x.id:05d}'
        if D(cost):s.add(Ledger(guild_id=guild,skin_id=x.id,kind='ACQUISITION',amount=-D(cost),note=source))
        if D(fees):s.add(Ledger(guild_id=guild,skin_id=x.id,kind='ACQUISITION_FEE',amount=-D(fees),note=source))
        return x
def reserve(guild,user,code,minutes=30):
    with Session.begin() as s:
        x=s.scalar(select(Skin).where(Skin.guild_id==guild,Skin.code==code.upper()).with_for_update())
        if not x or x.status!='AVAILABLE':raise ValueError('Skin indisponível ou já reservada.')
        x.status='RESERVED';x.reserved_by=user;x.reserved_until=datetime.now(timezone.utc)+timedelta(minutes=minutes)
        sale=Sale(code='PENDING',guild_id=guild,skin_id=x.id,buyer_id=user,sale_price=x.price,reserved_until=x.reserved_until);s.add(sale);s.flush();sale.code=f'VD-{sale.id:05d}';log(s,guild,user,'RESERVE','sale',sale.id,x.code);return sale,x
def sale_step(guild,actor,sale_code,new_status,fees=0):
    allowed={'RESERVED':{'PAYMENT_CONFIRMED','CANCELLED'},'PAYMENT_CONFIRMED':{'TRADE_SENT','CANCELLED'},'TRADE_SENT':{'COMPLETED'},'COMPLETED':set(),'CANCELLED':set()}
    with Session.begin() as s:
        sale=s.scalar(select(Sale).where(Sale.guild_id==guild,Sale.code==sale_code.upper()).with_for_update());
        if not sale:raise ValueError('Venda não encontrada.')
        if new_status not in allowed.get(sale.status,set()):raise ValueError(f'Transição inválida: {sale.status} → {new_status}.')
        skin=s.get(Skin,sale.skin_id);old=sale.status;sale.status=new_status
        if new_status=='CANCELLED':skin.status='AVAILABLE';skin.reserved_by=None;skin.reserved_until=None
        if new_status=='COMPLETED':
            sale.sale_fees=D(fees);sale.completed_at=datetime.now(timezone.utc);skin.status='SOLD';skin.sold_at=sale.completed_at
            s.add(Ledger(guild_id=guild,skin_id=skin.id,sale_id=sale.id,kind='SALE',amount=sale.sale_price,note=sale.code))
            if D(fees):s.add(Ledger(guild_id=guild,skin_id=skin.id,sale_id=sale.id,kind='SALE_FEE',amount=-D(fees),note=sale.code))
        log(s,guild,actor,'SALE_STATUS','sale',sale.id,f'{old}->{new_status}');return sale,skin
def transition_skin(guild,actor,code,new_status,note=None):
    allowed={'AVAILABLE':{'PERSONAL'},'PERSONAL':{'AVAILABLE'}}
    with Session.begin() as s:
        x=s.scalar(select(Skin).where(Skin.guild_id==guild,Skin.code==code.upper()).with_for_update())
        if not x:raise ValueError('Skin não encontrada.')
        if new_status not in allowed.get(x.status,set()):raise ValueError(f'Transição inválida: {x.status} → {new_status}.')
        old=x.status;x.status=new_status;x.withdrawn_at=datetime.now(timezone.utc) if new_status=='PERSONAL' else None;log(s,g,actor,'SKIN_STATUS','skin',x.id,f'{old}->{new_status}; {note or ""}');return x
def expire_reservations(guild=None):
    now=datetime.now(timezone.utc);n=0
    with Session.begin() as s:
        q=select(Sale).where(Sale.status=='RESERVED',Sale.reserved_until<now)
        if guild:q=q.where(Sale.guild_id==guild)
        for sale in s.scalars(q).all():
            sale.status='CANCELLED';skin=s.get(Skin,sale.skin_id);skin.status='AVAILABLE';skin.reserved_by=None;skin.reserved_until=None;n+=1
    return n
def matching_interests(skin):
    with Session() as s:rows=s.scalars(select(Interest).where(Interest.guild_id==skin.guild_id,Interest.active==True)).all()
    out=[]
    for i in rows:
        if i.skin_name.lower() not in skin.name.lower() and skin.name.lower() not in i.skin_name.lower():continue
        if i.exterior and skin.exterior and i.exterior.lower()!=skin.exterior.lower():continue
        if i.max_budget is not None and skin.price>i.max_budget:continue
        try:
            if i.max_float and Decimal(skin.floatv)>Decimal(i.max_float):continue
        except:pass
        out.append(i)
    return out
def intelligence(desired,quick_sale,fees,liquidity='Média',cash=None):
    desired,quick_sale,fees=D(desired),D(quick_sale),D(fees);profit=quick_sale-desired-fees;roi=(profit/desired*100) if desired else Decimal(0);impact=(desired/D(cash)*100) if cash and D(cash)>0 else None
    meets=profit>=20 and roi>=8 and liquidity.lower() not in ('baixa','low')
    return {'profit':profit,'roi':roi,'impact':impact,'meets':meets}
def dashboard(guild):
    expire_reservations(guild)
    with Session() as s:
        skins=s.scalars(select(Skin).where(Skin.guild_id==guild)).all();ledger=s.scalars(select(Ledger).where(Ledger.guild_id==guild)).all();fb=s.scalars(select(Feedback).where(Feedback.guild_id==guild)).all();pending=s.scalar(select(func.count()).select_from(Buylist).where(Buylist.guild_id==guild,Buylist.status.not_in(['COMPLETED','REJECTED']))) or 0
    avail=[x for x in skins if x.status in ('AVAILABLE','RESERVED')];sold=[x for x in skins if x.status=='SOLD'];capital=sum((x.cost+x.acquisition_fees for x in avail),Decimal(0));stock=sum((x.price for x in avail),Decimal(0));cash=sum((x.amount for x in ledger),Decimal(0));revenue=sum((x.amount for x in ledger if x.kind=='SALE'),Decimal(0));costs=-sum((x.amount for x in ledger if x.kind in ('ACQUISITION','ACQUISITION_FEE','SALE_FEE')),Decimal(0));profit=cash
    return {'available':sum(x.status=='AVAILABLE' for x in skins),'reserved':sum(x.status=='RESERVED' for x in skins),'sold':len(sold),'personal':sum(x.status=='PERSONAL' for x in skins),'capital':capital,'stock_value':stock,'cash':cash,'revenue':revenue,'costs':costs,'profit':profit,'pending_buylist':pending,'rating':(sum(x.rating for x in fb)/len(fb) if fb else 0),'feedbacks':len(fb)}
