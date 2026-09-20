from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from .config import DATABASE_URL
url=DATABASE_URL
if url.startswith("postgres://"): url="postgresql+psycopg://"+url[len("postgres://"):]
elif url.startswith("postgresql://") and "+psycopg" not in url: url="postgresql+psycopg://"+url[len("postgresql://"):]
engine=create_engine(url,pool_pre_ping=True,future=True)
Session=sessionmaker(engine,expire_on_commit=False)
class Base(DeclarativeBase): pass
def init_db():
    try:
        import clutch_os.core.models_ext  # register V3 tables
    except Exception:
        pass
    from . import models
    Base.metadata.create_all(engine)
    _compat_migrate()


def _compat_migrate():
    """Small additive migration so a V3.2 local DB can boot V3.3 without losing data."""
    wanted={
      'orders': [('customer_id','INTEGER'),('assigned_to','BIGINT'),('found_price','NUMERIC(14,2)'),('customer_price','NUMERIC(14,2)'),('supplier','VARCHAR(80)'),('found_float','VARCHAR(32)'),('inspect_link','TEXT'),('listing_url','TEXT'),('proposal_expires_at','TIMESTAMP'),('customer_accepted_at','TIMESTAMP'),('trade_lock_until','TIMESTAMP'),('updated_at','TIMESTAMP')],
      'operations_queue':[('assigned_to','BIGINT')],
      'customers':[('whatsapp','VARCHAR(40)'),('notes','TEXT')]
    }
    with engine.begin() as c:
        ins=inspect(c)
        tables=set(ins.get_table_names())
        for table,cols in wanted.items():
            if table not in tables: continue
            existing={x['name'] for x in ins.get_columns(table)}
            for name,typ in cols:
                if name not in existing:
                    c.execute(text(f'ALTER TABLE {table} ADD COLUMN {name} {typ}'))
