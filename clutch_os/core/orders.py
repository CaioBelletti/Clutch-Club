from sqlalchemy import select
from clutch_bot.db import Session
from clutch_bot.models import Order, Operation, Audit
from clutch_os.core.models_ext import Customer
from clutch_bot.services import D

class OrderService:
    @staticmethod
    def create(guild_id:int, discord_id:int, display_name:str, skin_name:str, exterior=None, max_float=None, budget=None, notes=None):
        """Canonical transaction: Customer + Order + Operation are committed together."""
        with Session.begin() as s:
            c=s.scalar(select(Customer).where(Customer.guild_id==guild_id,Customer.discord_id==discord_id))
            if not c:
                c=Customer(guild_id=guild_id,discord_id=discord_id,code='PENDING',display_name=display_name or f'Discord {discord_id}')
                s.add(c);s.flush();c.code=f'CL-{c.id:05d}'
            o=Order(code='PENDING',guild_id=guild_id,user_id=discord_id,customer_id=c.id,skin_name=skin_name,
                    exterior=(exterior or '').upper() or None,max_float=max_float or None,budget=D(budget) if budget else None,
                    notes=notes or None,status='OPEN')
            s.add(o);s.flush();o.code=f'ENC-{o.id:05d}'
            detail=f'**Skin:** {skin_name}\n**Exterior:** {o.exterior or "—"}\n**Float máx.:** {max_float or "—"}\n**Orçamento:** {o.budget if o.budget is not None else "—"}\n**Observações:** {notes or "—"}'
            op=Operation(guild_id=guild_id,kind='ORDER',ref_code=o.code,entity_id=o.id,user_id=discord_id,title=f'ENCOMENDA — {o.code}',detail=detail,status='OPEN',priority='HIGH')
            s.add(op)
            s.add(Audit(guild_id=guild_id,actor_id=discord_id,action='ORDER_PIPELINE_CREATE',entity_type='order',entity_id=o.id,detail=f'{o.code}; customer={c.code}'))
            s.flush()
            return {'order_id':o.id,'code':o.code,'customer_id':c.id,'customer_code':c.code,'operation_id':op.id}

    @staticmethod
    def get(guild_id:int, code:str):
        with Session() as s:
            return s.scalar(select(Order).where(Order.guild_id==guild_id,Order.code==code.upper()))
