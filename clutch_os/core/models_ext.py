from datetime import datetime, timezone
from decimal import Decimal
from sqlalchemy import String,Integer,BigInteger,Text,DateTime,Numeric,Boolean,UniqueConstraint
from sqlalchemy.orm import Mapped,mapped_column
from clutch_bot.db import Base

def utc(): return datetime.now(timezone.utc)

class Customer(Base):
    __tablename__='customers'
    id:Mapped[int]=mapped_column(primary_key=True); guild_id:Mapped[int]=mapped_column(BigInteger,index=True); discord_id:Mapped[int]=mapped_column(BigInteger,index=True)
    code:Mapped[str]=mapped_column(String(24),index=True); display_name:Mapped[str|None]=mapped_column(String(120)); trade_url:Mapped[str|None]=mapped_column(Text); whatsapp:Mapped[str|None]=mapped_column(String(40)); notes:Mapped[str|None]=mapped_column(Text)
    completed_buys:Mapped[int]=mapped_column(Integer,default=0); completed_sells:Mapped[int]=mapped_column(Integer,default=0); volume:Mapped[Decimal]=mapped_column(Numeric(14,2),default=0); created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utc)
    __table_args__=(UniqueConstraint('guild_id','discord_id',name='uq_customer_guild_discord'),UniqueConstraint('guild_id','code',name='uq_customer_code'))

class Account(Base):
    __tablename__='accounts'
    id:Mapped[int]=mapped_column(primary_key=True); guild_id:Mapped[int]=mapped_column(BigInteger,index=True); code:Mapped[str]=mapped_column(String(32)); name:Mapped[str]=mapped_column(String(100)); kind:Mapped[str]=mapped_column(String(24)); active:Mapped[bool]=mapped_column(Boolean,default=True)
    __table_args__=(UniqueConstraint('guild_id','code',name='uq_account_code'),)

class JournalEntry(Base):
    __tablename__='journal_entries'
    id:Mapped[int]=mapped_column(primary_key=True); guild_id:Mapped[int]=mapped_column(BigInteger,index=True); code:Mapped[str]=mapped_column(String(24),index=True); event_key:Mapped[str]=mapped_column(String(80),unique=True,index=True); memo:Mapped[str|None]=mapped_column(Text); created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utc)

class JournalLine(Base):
    __tablename__='journal_lines'
    id:Mapped[int]=mapped_column(primary_key=True); entry_id:Mapped[int]=mapped_column(Integer,index=True); account_code:Mapped[str]=mapped_column(String(32),index=True); debit:Mapped[Decimal]=mapped_column(Numeric(14,2),default=0); credit:Mapped[Decimal]=mapped_column(Numeric(14,2),default=0); skin_id:Mapped[int|None]=mapped_column(Integer,index=True)

class DomainEvent(Base):
    __tablename__='domain_events'
    id:Mapped[int]=mapped_column(primary_key=True); guild_id:Mapped[int]=mapped_column(BigInteger,index=True); event_key:Mapped[str]=mapped_column(String(100),unique=True,index=True); event_type:Mapped[str]=mapped_column(String(60),index=True); entity_type:Mapped[str]=mapped_column(String(40)); entity_id:Mapped[int|None]=mapped_column(Integer); payload:Mapped[str|None]=mapped_column(Text); processed:Mapped[bool]=mapped_column(Boolean,default=False,index=True); created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utc)

class StaffRole(Base):
    __tablename__='staff_roles'
    id:Mapped[int]=mapped_column(primary_key=True); guild_id:Mapped[int]=mapped_column(BigInteger,index=True); discord_id:Mapped[int]=mapped_column(BigInteger,index=True); role:Mapped[str]=mapped_column(String(24)); active:Mapped[bool]=mapped_column(Boolean,default=True)
    __table_args__=(UniqueConstraint('guild_id','discord_id',name='uq_staff_role'),)

class RiskRule(Base):
    __tablename__='risk_rules'
    guild_id:Mapped[int]=mapped_column(BigInteger,primary_key=True); key:Mapped[str]=mapped_column(String(64),primary_key=True); value:Mapped[str]=mapped_column(String(100)); updated_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utc)
