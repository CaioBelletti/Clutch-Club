from datetime import datetime, timezone
from decimal import Decimal
from sqlalchemy import String,Integer,BigInteger,Text,DateTime,Numeric,ForeignKey,Boolean
from sqlalchemy.orm import Mapped,mapped_column
from .db import Base

def utc(): return datetime.now(timezone.utc)

class Skin(Base):
    __tablename__='skins'
    id:Mapped[int]=mapped_column(primary_key=True); code:Mapped[str]=mapped_column(String(24),unique=True,index=True)
    guild_id:Mapped[int]=mapped_column(BigInteger,index=True); name:Mapped[str]=mapped_column(String(180),index=True)
    exterior:Mapped[str|None]=mapped_column(String(40)); floatv:Mapped[str|None]=mapped_column(String(32)); pattern:Mapped[str|None]=mapped_column(String(32)); stickers:Mapped[str|None]=mapped_column(Text)
    inspect:Mapped[str|None]=mapped_column(Text); image_url:Mapped[str|None]=mapped_column(Text); status:Mapped[str]=mapped_column(String(32),default='AVAILABLE',index=True)
    cost:Mapped[Decimal]=mapped_column(Numeric(14,2),default=0); acquisition_fees:Mapped[Decimal]=mapped_column(Numeric(14,2),default=0); price:Mapped[Decimal]=mapped_column(Numeric(14,2),default=0)
    source:Mapped[str|None]=mapped_column(String(40)); source_ref:Mapped[str|None]=mapped_column(String(40)); reserved_by:Mapped[int|None]=mapped_column(BigInteger); reserved_until:Mapped[datetime|None]=mapped_column(DateTime(timezone=True))
    channel_id:Mapped[int|None]=mapped_column(BigInteger); message_id:Mapped[int|None]=mapped_column(BigInteger); created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utc)
    sold_at:Mapped[datetime|None]=mapped_column(DateTime(timezone=True)); withdrawn_at:Mapped[datetime|None]=mapped_column(DateTime(timezone=True))

class Buylist(Base):
    __tablename__='buylist'
    id:Mapped[int]=mapped_column(primary_key=True); code:Mapped[str]=mapped_column(String(24),unique=True,index=True); guild_id:Mapped[int]=mapped_column(BigInteger,index=True); user_id:Mapped[int]=mapped_column(BigInteger,index=True)
    skin_name:Mapped[str]=mapped_column(String(180)); exterior:Mapped[str]=mapped_column(String(40)); floatv:Mapped[str]=mapped_column(String(32)); pattern:Mapped[str|None]=mapped_column(String(32)); stickers:Mapped[str|None]=mapped_column(Text)
    desired_price:Mapped[Decimal|None]=mapped_column(Numeric(14,2)); proposal:Mapped[Decimal|None]=mapped_column(Numeric(14,2)); counterproposal:Mapped[Decimal|None]=mapped_column(Numeric(14,2)); proposal_expires_at:Mapped[datetime|None]=mapped_column(DateTime(timezone=True))
    status:Mapped[str]=mapped_column(String(32),default='PENDING',index=True); ticket_channel_id:Mapped[int|None]=mapped_column(BigInteger); message_id:Mapped[int|None]=mapped_column(BigInteger); stock_skin_id:Mapped[int|None]=mapped_column(ForeignKey('skins.id')); created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utc)

class Sale(Base):
    __tablename__='sales'
    id:Mapped[int]=mapped_column(primary_key=True); code:Mapped[str]=mapped_column(String(24),unique=True,index=True); guild_id:Mapped[int]=mapped_column(BigInteger,index=True); skin_id:Mapped[int]=mapped_column(ForeignKey('skins.id'),index=True); buyer_id:Mapped[int]=mapped_column(BigInteger,index=True)
    status:Mapped[str]=mapped_column(String(32),default='RESERVED',index=True); sale_price:Mapped[Decimal]=mapped_column(Numeric(14,2)); sale_fees:Mapped[Decimal]=mapped_column(Numeric(14,2),default=0); reserved_until:Mapped[datetime|None]=mapped_column(DateTime(timezone=True)); created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utc); completed_at:Mapped[datetime|None]=mapped_column(DateTime(timezone=True))

class Interest(Base):
    __tablename__='product_interests'
    id:Mapped[int]=mapped_column(primary_key=True); guild_id:Mapped[int]=mapped_column(BigInteger,index=True); user_id:Mapped[int]=mapped_column(BigInteger,index=True); skin_name:Mapped[str]=mapped_column(String(180),index=True); exterior:Mapped[str|None]=mapped_column(String(40)); max_budget:Mapped[Decimal|None]=mapped_column(Numeric(14,2)); max_float:Mapped[str|None]=mapped_column(String(32)); active:Mapped[bool]=mapped_column(Boolean,default=True); created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utc)

class Order(Base):
    __tablename__='orders'
    id:Mapped[int]=mapped_column(primary_key=True); code:Mapped[str]=mapped_column(String(24),unique=True); guild_id:Mapped[int]=mapped_column(BigInteger,index=True); user_id:Mapped[int]=mapped_column(BigInteger); customer_id:Mapped[int|None]=mapped_column(Integer,index=True); skin_name:Mapped[str]=mapped_column(String(180)); exterior:Mapped[str|None]=mapped_column(String(40)); max_float:Mapped[str|None]=mapped_column(String(32)); budget:Mapped[Decimal|None]=mapped_column(Numeric(14,2)); notes:Mapped[str|None]=mapped_column(Text); status:Mapped[str]=mapped_column(String(32),default='OPEN',index=True); assigned_to:Mapped[int|None]=mapped_column(BigInteger); found_price:Mapped[Decimal|None]=mapped_column(Numeric(14,2)); customer_price:Mapped[Decimal|None]=mapped_column(Numeric(14,2)); supplier:Mapped[str|None]=mapped_column(String(80)); found_float:Mapped[str|None]=mapped_column(String(32)); inspect_link:Mapped[str|None]=mapped_column(Text); listing_url:Mapped[str|None]=mapped_column(Text); proposal_expires_at:Mapped[datetime|None]=mapped_column(DateTime(timezone=True)); customer_accepted_at:Mapped[datetime|None]=mapped_column(DateTime(timezone=True)); trade_lock_until:Mapped[datetime|None]=mapped_column(DateTime(timezone=True)); updated_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utc,onupdate=utc); created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utc)

class Feedback(Base):
    __tablename__='feedback'
    id:Mapped[int]=mapped_column(primary_key=True); guild_id:Mapped[int]=mapped_column(BigInteger,index=True); user_id:Mapped[int]=mapped_column(BigInteger,index=True); sale_id:Mapped[int|None]=mapped_column(ForeignKey('sales.id')); rating:Mapped[int]=mapped_column(Integer); comment:Mapped[str|None]=mapped_column(Text); created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utc)

class Ledger(Base):
    __tablename__='ledger'
    id:Mapped[int]=mapped_column(primary_key=True); guild_id:Mapped[int]=mapped_column(BigInteger,index=True); skin_id:Mapped[int|None]=mapped_column(ForeignKey('skins.id')); sale_id:Mapped[int|None]=mapped_column(ForeignKey('sales.id')); kind:Mapped[str]=mapped_column(String(32),index=True); amount:Mapped[Decimal]=mapped_column(Numeric(14,2)); note:Mapped[str|None]=mapped_column(Text); created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utc)

class Audit(Base):
    __tablename__='audit_log'
    id:Mapped[int]=mapped_column(primary_key=True); guild_id:Mapped[int]=mapped_column(BigInteger,index=True); actor_id:Mapped[int]=mapped_column(BigInteger); action:Mapped[str]=mapped_column(String(80)); entity_type:Mapped[str]=mapped_column(String(40)); entity_id:Mapped[int|None]=mapped_column(Integer); detail:Mapped[str|None]=mapped_column(Text); created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utc)

class Panel(Base):
    __tablename__='persistent_panels'
    guild_id:Mapped[int]=mapped_column(BigInteger,primary_key=True); panel_key:Mapped[str]=mapped_column(String(32),primary_key=True); channel_id:Mapped[int]=mapped_column(BigInteger); message_id:Mapped[int]=mapped_column(BigInteger)

class GuildConfig(Base):
    __tablename__='guild_config'
    guild_id:Mapped[int]=mapped_column(BigInteger,primary_key=True); key:Mapped[str]=mapped_column(String(64),primary_key=True); value:Mapped[str]=mapped_column(Text)


class Operation(Base):
    __tablename__='operations_queue'
    id:Mapped[int]=mapped_column(primary_key=True)
    guild_id:Mapped[int]=mapped_column(BigInteger,index=True)
    kind:Mapped[str]=mapped_column(String(32),index=True)
    ref_code:Mapped[str]=mapped_column(String(32),index=True)
    entity_id:Mapped[int|None]=mapped_column(Integer)
    user_id:Mapped[int|None]=mapped_column(BigInteger,index=True)
    title:Mapped[str]=mapped_column(String(220))
    detail:Mapped[str|None]=mapped_column(Text)
    status:Mapped[str]=mapped_column(String(32),default='OPEN',index=True)
    priority:Mapped[str]=mapped_column(String(16),default='NORMAL',index=True)
    staff_channel_id:Mapped[int|None]=mapped_column(BigInteger)
    staff_message_id:Mapped[int|None]=mapped_column(BigInteger)
    assigned_to:Mapped[int|None]=mapped_column(BigInteger,index=True)
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utc)
    updated_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utc,onupdate=utc)


class Negotiation(Base):
    __tablename__='negotiations'
    id:Mapped[int]=mapped_column(primary_key=True); code:Mapped[str]=mapped_column(String(24),unique=True,index=True); guild_id:Mapped[int]=mapped_column(BigInteger,index=True); user_id:Mapped[int]=mapped_column(BigInteger,index=True)
    kind:Mapped[str]=mapped_column(String(32),default='TRADE_IN',index=True); status:Mapped[str]=mapped_column(String(32),default='OPEN',index=True); sale_total:Mapped[Decimal]=mapped_column(Numeric(14,2),default=0); trade_credit:Mapped[Decimal]=mapped_column(Numeric(14,2),default=0); cash_due:Mapped[Decimal]=mapped_column(Numeric(14,2),default=0); cash_received:Mapped[Decimal]=mapped_column(Numeric(14,2),default=0); notes:Mapped[str|None]=mapped_column(Text); created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utc); updated_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utc,onupdate=utc)

class NegotiationOrder(Base):
    __tablename__='negotiation_orders'
    id:Mapped[int]=mapped_column(primary_key=True); negotiation_id:Mapped[int]=mapped_column(ForeignKey('negotiations.id'),index=True); order_id:Mapped[int]=mapped_column(ForeignKey('orders.id'),index=True)

class TradeInItem(Base):
    __tablename__='tradein_items'
    id:Mapped[int]=mapped_column(primary_key=True); negotiation_id:Mapped[int]=mapped_column(ForeignKey('negotiations.id'),index=True); code:Mapped[str]=mapped_column(String(24),unique=True,index=True); name:Mapped[str]=mapped_column(String(180)); exterior:Mapped[str|None]=mapped_column(String(40)); floatv:Mapped[str|None]=mapped_column(String(32)); pattern:Mapped[str|None]=mapped_column(String(32)); credit_value:Mapped[Decimal]=mapped_column(Numeric(14,2),default=0); status:Mapped[str]=mapped_column(String(32),default='EXPECTED',index=True); stock_skin_id:Mapped[int|None]=mapped_column(ForeignKey('skins.id')); created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utc)

class NegotiationPayment(Base):
    __tablename__='negotiation_payments'
    id:Mapped[int]=mapped_column(primary_key=True); negotiation_id:Mapped[int]=mapped_column(ForeignKey('negotiations.id'),index=True); kind:Mapped[str]=mapped_column(String(24)); amount:Mapped[Decimal]=mapped_column(Numeric(14,2)); status:Mapped[str]=mapped_column(String(24),default='PENDING'); reference:Mapped[str|None]=mapped_column(String(120)); created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utc)
