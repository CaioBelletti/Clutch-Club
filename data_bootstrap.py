from pathlib import Path
from datetime import datetime, timezone
import os, shutil, sqlite3, json, re, subprocess, sys

ROOT=Path(__file__).resolve().parent
SHARED=ROOT.parent/'Clutch_OS_DATA'
TARGET=SHARED/'clutch_v2.db'
REPORT=SHARED/'migration_report_v3_4_5.json'
MARKER=SHARED/'migration_v3_4_5_done.json'
STAMP=datetime.now().strftime('%Y%m%d_%H%M%S')
VERSION='3.4.5'
DEFAULT_CANONICAL_GUILD_ID=1549553223470416022

KEYS={
 'orders':['guild_id','code'],'customers':['guild_id','code'],'operations_queue':['guild_id','kind','ref_code'],
 'guild_config':['guild_id','key'],'persistent_panels':['guild_id','panel_key'],'skins':['code'],
 'buylist':['code'],'sales':['code'],'negotiations':['code'],'tradein_items':['code'],
 'accounts':['guild_id','code'],'journal_entries':['event_key'],'domain_events':['event_key'],
 'staff_roles':['guild_id','discord_id'],'risk_rules':['guild_id','key']
}

def qid(s): return '"'+str(s).replace('"','""')+'"'
def tables(con): return {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")}
def info(con,t): return con.execute(f'PRAGMA table_info({qid(t)})').fetchall()
def count(con,t):
    try:return con.execute(f'SELECT COUNT(*) FROM {qid(t)}').fetchone()[0]
    except:return 0

def columns(con,t):
    return {x[1] for x in info(con,t)} if t in tables(con) else set()

def has_columns(con,t,*cols):
    cs=columns(con,t); return all(x in cs for x in cols)

def open_ro(p):
    return sqlite3.connect(f'file:{p.as_posix()}?mode=ro',uri=True,timeout=5)

def inspect_db(p):
    rec={'path':str(p),'valid':False,'tables':{},'order_codes':[],'operation_order_codes':[],'error':None}
    try:
        c=open_ro(p); ts=tables(c); chk=c.execute('PRAGMA integrity_check').fetchone()[0]
        if chk!='ok': raise RuntimeError(str(chk))
        rec['valid']=True
        rec['tables']={t:count(c,t) for t in sorted(ts)}
        if 'orders' in ts:
            rec['order_codes']=[str(x[0]) for x in c.execute("SELECT code FROM orders WHERE code LIKE 'ENC-%' AND code IS NOT NULL")]
        if 'operations_queue' in ts:
            rec['operation_order_codes']=[str(x[0]) for x in c.execute("SELECT ref_code FROM operations_queue WHERE UPPER(kind)='ORDER' AND ref_code LIKE 'ENC-%' AND ref_code IS NOT NULL")]
        c.close()
    except Exception as e: rec['error']=f'{type(e).__name__}: {e}'
    return rec

def _sqlite_file(p):
    try:
        if not p.is_file() or p.stat().st_size < 4096: return False
        with p.open('rb') as f: return f.read(16) == b'SQLite format 3\x00'
    except: return False

def discovery_roots():
    # The build is expected directly under boot, but tolerate one extra wrapper directory.
    roots=[]
    for r in (ROOT.parent, ROOT.parent.parent):
        try:
            rr=r.resolve()
            if rr not in roots and rr.exists(): roots.append(rr)
        except: pass
    # Prefer the root that actually contains Clutch_OS_* sibling builds.
    scored=[]
    for r in roots:
        try: score=sum(1 for x in r.iterdir() if x.is_dir() and x.name.lower().startswith('clutch_os_'))
        except: score=0
        scored.append((score,r))
    scored.sort(key=lambda x:x[0],reverse=True)
    return [r for _,r in scored]

def discover_sources():
    # Forensics discovery: scan every file by SQLite header, not only files literally named clutch_v2.db.
    found=[];seen=set(); excluded=[]
    roots=discovery_roots()
    print('[FORENSICS] Roots: '+ ' | '.join(str(x) for x in roots))
    for root in roots:
        try: iterator=root.rglob('*')
        except: continue
        for p in iterator:
            try:
                rp=p.resolve()
                if rp in seen: continue
                seen.add(rp)
                # Never ingest the active canonical DB or temporary staging files. Historical
                # clutch_v2_pre_* backups inside Clutch_OS_DATA are intentionally eligible.
                if rp == TARGET.resolve() or p.name.startswith('.clutch_'):
                    if _sqlite_file(p): excluded.append(str(p))
                    continue
                if ROOT.resolve() in rp.parents or rp==ROOT.resolve(): continue
                if _sqlite_file(p):
                    # Ignore unrelated SQLite applications: a Clutch source must expose at least
                    # one core table. This prevents Belletti PDV databases entering recovery.
                    try:
                        cc=open_ro(p); tt=tables(cc); cc.close()
                        if tt & {'orders','operations_queue','customers','skins','guild_config','persistent_panels','negotiations','tradein_items'}:
                            found.append(p)
                    except: pass
            except: pass
    print(f'[FORENSICS] SQLite históricos encontrados: {len(found)}')
    for p in sorted(found,key=lambda x:str(x).lower()): print(f'[FORENSICS] DB: {p}')
    return sorted(found,key=lambda p:str(p).lower())

def create_schema(stage):
    if stage.exists(): stage.unlink()
    env=os.environ.copy(); env['DATABASE_URL']='sqlite:///'+str(stage).replace('\\','/')
    r=subprocess.run([sys.executable,'-c','from clutch_bot.db import init_db; init_db()'],cwd=ROOT,env=env,capture_output=True,text=True)
    if r.returncode!=0: raise RuntimeError('Falha criando schema temporário: '+(r.stderr or r.stdout)[-1200:])

def normalize(meta,val,col):
    notnull=bool(meta[3]); default=meta[4]; typ=(meta[2] or '').upper()
    if val is not None:return val
    if not notnull:return None
    if col in ('created_at','updated_at'):return datetime.now(timezone.utc).isoformat()
    if default is not None:
        d=str(default).strip("'\"")
        if d.upper()=='CURRENT_TIMESTAMP':return datetime.now(timezone.utc).isoformat()
        if d.upper()!='NULL':return d
    if any(x in typ for x in ('INT','NUM','REAL','DEC','FLOAT','BOOL')):return 0
    return ''

def exists_by_key(dst,t,row):
    keys=KEYS.get(t)
    if not keys or any(row.get(k) is None for k in keys):return False
    return dst.execute(f'SELECT 1 FROM {qid(t)} WHERE '+ ' AND '.join(f'{qid(k)}=?' for k in keys)+' LIMIT 1',[row[k] for k in keys]).fetchone() is not None

def merge_source(src_path,stage,report):
    src=open_ro(src_path); src.row_factory=sqlite3.Row
    dst=sqlite3.connect(stage,timeout=30); dst.execute('PRAGMA foreign_keys=OFF'); dst.execute('PRAGMA busy_timeout=30000')
    st=tables(src); dt=tables(dst); sr={'path':str(src_path),'tables':{}}
    try:
        dst.execute('BEGIN IMMEDIATE')
        for t in sorted(st & dt):
            dmeta={x[1]:x for x in info(dst,t)}; dcols=list(dmeta); before=count(dst,t); ins=skip=0
            for rr in src.execute(f'SELECT * FROM {qid(t)}'):
                row=dict(rr)
                if exists_by_key(dst,t,row): skip+=1; continue
                fields=[];vals=[]
                for c in dcols:
                    if c in row: fields.append(c);vals.append(normalize(dmeta[c],row[c],c))
                    elif c!='id' and bool(dmeta[c][3]): fields.append(c);vals.append(normalize(dmeta[c],None,c))
                # Snapshot DBs commonly reuse integer PKs. For natural-key entities, preserve the
                # business record and let SQLite allocate a new PK rather than discarding it.
                if 'id' in fields:
                    ix=fields.index('id'); pk=vals[ix]
                    if pk is not None and dst.execute(f'SELECT 1 FROM {qid(t)} WHERE id=?',(pk,)).fetchone():
                        if t in KEYS: fields.pop(ix); vals.pop(ix)
                        else: skip+=1; continue
                if not fields:continue
                try:
                    dst.execute(f'INSERT INTO {qid(t)} ({",".join(qid(c) for c in fields)}) VALUES ({",".join("?" for _ in fields)})',vals);ins+=1
                except sqlite3.IntegrityError:skip+=1
            sr['tables'][t]={'source':count(src,t),'before':before,'inserted':ins,'skipped':skip,'after':count(dst,t)}
        dst.commit()
    except: dst.rollback();raise
    finally: src.close();dst.close()
    report['sources'].append(sr)

def field(detail,label):
    if not detail:return None
    m=re.search(r'\*\*'+re.escape(label)+r':\*\*\s*(?:\*\*)?([^\n*]+)',detail,re.I)
    if not m:return None
    v=m.group(1).strip().strip('*').strip()
    return None if v in ('—','-','') else v

def num(v):
    if not v:return None
    s=re.sub(r'[^0-9,.-]','',str(v)).replace('.','').replace(',','.')
    try:return float(s)
    except:return None

def ensure_customer(dst,guild,user_id):
    if not user_id:return None
    r=dst.execute('SELECT id FROM customers WHERE guild_id=? AND discord_id=? LIMIT 1',(guild,user_id)).fetchone()
    if r:return r[0]
    mx=dst.execute('SELECT COALESCE(MAX(id),0)+1 FROM customers').fetchone()[0]
    code=f'CL-{mx:05d}'
    dst.execute('INSERT INTO customers (code,guild_id,discord_id,display_name,completed_buys,completed_sells,volume,created_at) VALUES (?,?,?,?,0,0,0,?)',(code,guild,user_id,f'Discord {user_id}',datetime.now(timezone.utc).isoformat()))
    return dst.execute('SELECT id FROM customers WHERE guild_id=? AND discord_id=?',(guild,user_id)).fetchone()[0]

def reconcile_pipeline(stage,report):
    dst=sqlite3.connect(stage); dst.row_factory=sqlite3.Row; repaired=[]
    try:
        dst.execute('BEGIN IMMEDIATE')
        ops=dst.execute("SELECT * FROM operations_queue WHERE UPPER(kind)='ORDER' AND ref_code LIKE 'ENC-%' ORDER BY id").fetchall()
        for op in ops:
            code=op['ref_code']; guild=op['guild_id']; o=dst.execute('SELECT * FROM orders WHERE guild_id=? AND code=?',(guild,code)).fetchone()
            cid=ensure_customer(dst,guild,op['user_id'])
            if not o:
                detail=op['detail'] or ''
                skin=field(detail,'Skin') or (op['title'] or '').replace('ENCOMENDA —','').strip() or 'Encomenda recuperada'
                exterior=field(detail,'Exterior'); maxfloat=field(detail,'Float máx.')
                budget=num(field(detail,'Orçamento')); notes=field(detail,'Observações')
                status='DELIVERED' if str(op['status']).upper() in ('DONE','DELIVERED','COMPLETED') or 'ENTREGUE' in detail.upper() else 'OPEN'
                now=op['created_at'] or datetime.now(timezone.utc).isoformat()
                dst.execute('INSERT INTO orders (code,guild_id,user_id,customer_id,skin_name,exterior,max_float,budget,notes,status,updated_at,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',(code,guild,op['user_id'] or 0,cid,skin,exterior,maxfloat,budget,notes,status,now,now))
                oid=dst.execute('SELECT id FROM orders WHERE guild_id=? AND code=?',(guild,code)).fetchone()[0]
                dst.execute('UPDATE operations_queue SET entity_id=? WHERE id=?',(oid,op['id']))
                repaired.append(code)
            else:
                oid=o['id']
                # customer_id is a local integer PK and may change while consolidating snapshots.
                # user_id/discord_id is the stable cross-database identity, so always reconcile by it.
                if cid and o['customer_id']!=cid: dst.execute('UPDATE orders SET customer_id=? WHERE id=?',(cid,oid))
                if op['entity_id']!=oid: dst.execute('UPDATE operations_queue SET entity_id=? WHERE id=?',(oid,op['id']))
        # Reconcile customer FK for every imported Order, including Orders that had no legacy Operation.
        for o in dst.execute('SELECT * FROM orders').fetchall():
            cid=ensure_customer(dst,o['guild_id'],o['user_id'])
            if cid and o['customer_id']!=cid: dst.execute('UPDATE orders SET customer_id=? WHERE id=?',(cid,o['id']))
        # Any order without an operation gets a canonical operational record (unless terminal).
        rows=dst.execute("SELECT * FROM orders WHERE status NOT IN ('DELIVERED','CANCELLED')").fetchall()
        for o in rows:
            if not dst.execute("SELECT 1 FROM operations_queue WHERE guild_id=? AND UPPER(kind)='ORDER' AND ref_code=?",(o['guild_id'],o['code'])).fetchone():
                dst.execute('INSERT INTO operations_queue (guild_id,kind,ref_code,entity_id,user_id,title,detail,status,priority,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)',(o['guild_id'],'ORDER',o['code'],o['id'],o['user_id'],f"ENCOMENDA — {o['code']}",f"**Skin:** {o['skin_name']}",'OPEN','HIGH',o['created_at'] or datetime.now(timezone.utc).isoformat(),datetime.now(timezone.utc).isoformat()))
        dst.commit()
    except:dst.rollback();raise
    finally:dst.close()
    report['reconstructed_orders']=repaired

def validate(stage,detected):
    c=sqlite3.connect(stage);ts=tables(c);errors=[];metrics={t:count(c,t) for t in sorted(ts)}
    integ=c.execute('PRAGMA integrity_check').fetchone()[0]
    if integ!='ok':errors.append('SQLite integrity_check: '+str(integ))
    canonical=set(x[0] for x in c.execute("SELECT code FROM orders WHERE code LIKE 'ENC-%'")) if 'orders' in ts else set()
    missing=sorted(set(detected)-canonical)
    if missing:errors.append('Encomendas históricas detectadas e ausentes no Core: '+', '.join(missing))
    if 'orders' in ts and 'customers' in ts:
        bad=c.execute('SELECT COUNT(*) FROM orders o LEFT JOIN customers c ON c.id=o.customer_id WHERE o.customer_id IS NULL OR c.id IS NULL').fetchone()[0]
        if bad:errors.append(f'{bad} order(s) sem CRM canônico')
    if 'operations_queue' in ts and 'orders' in ts:
        bad=c.execute("SELECT COUNT(*) FROM operations_queue op LEFT JOIN orders o ON o.guild_id=op.guild_id AND o.code=op.ref_code WHERE UPPER(op.kind)='ORDER' AND o.id IS NULL").fetchone()[0]
        if bad:errors.append(f'{bad} operação(ões) ORDER órfã(s)')
    c.close();return not errors,metrics,errors,missing

def guild_inventory(db_path):
    out={}
    try:
        c=open_ro(db_path); ts=tables(c)
        for t in ('orders','operations_queue','customers','guild_config','persistent_panels','skins','negotiations'):
            if t not in ts: continue
            cols={x[1] for x in info(c,t)}
            if 'guild_id' not in cols: continue
            out[t]={str(g):n for g,n in c.execute(f'SELECT guild_id,COUNT(*) FROM {qid(t)} GROUP BY guild_id')}
        c.close()
    except Exception as e: out['error']=str(e)
    return out

def _load_local_env():
    """Load only the few bootstrap settings needed before bot/config imports."""
    env_file=ROOT/'.env'
    if not env_file.exists(): return
    try:
        for raw in env_file.read_text(encoding='utf-8-sig').splitlines():
            line=raw.strip()
            if not line or line.startswith('#') or '=' not in line: continue
            k,v=line.split('=',1); k=k.strip(); v=v.strip().strip('"').strip("'")
            if k and k not in os.environ: os.environ[k]=v
    except Exception as e:
        print(f'[BOOT] Aviso ao ler .env: {e}')

def primary_guild(stage):
    _load_local_env()
    # Migration identity is deliberately separate from legacy GUILD_ID. A stale GUILD_ID
    # caused records to be moved into 1549553223470416022 in older builds.
    env=os.getenv('CANONICAL_GUILD_ID','').strip()
    if env.isdigit() and int(env)>0: return int(env),'ENV:CANONICAL_GUILD_ID'
    return DEFAULT_CANONICAL_GUILD_ID,'CLUTCH_CLUB_CANONICAL'

def _merge_customer_alias(c, source_guild, target):
    """Move customer identities across legacy schemas without assuming FK column names."""
    if not has_columns(c,'customers','id','guild_id'): return 0,0
    cc=columns(c,'customers')
    select=['id']+[x for x in ('discord_id','code') if x in cc]
    rows=c.execute(f'SELECT {",".join(qid(x) for x in select)} FROM customers WHERE guild_id=?',(source_guild,)).fetchall()
    moved=merged=0
    for raw in rows:
        row=dict(zip(select,raw)); rid=row['id']; clauses=[];vals=[]
        if row.get('discord_id') not in (None,''): clauses.append('discord_id=?');vals.append(row['discord_id'])
        if row.get('code') not in (None,''): clauses.append('code=?');vals.append(row['code'])
        existing=None
        if clauses:
            existing=c.execute('SELECT id FROM customers WHERE guild_id=? AND ('+' OR '.join(clauses)+') ORDER BY id LIMIT 1',[target]+vals).fetchone()
        if existing:
            keep=existing[0]
            # Update only relationships that really contain customer_id in this schema.
            for rel in ('orders','negotiations','sales','buylist'):
                if has_columns(c,rel,'customer_id'):
                    c.execute(f'UPDATE {qid(rel)} SET customer_id=? WHERE customer_id=?',(keep,rid))
            c.execute('DELETE FROM customers WHERE id=?',(rid,)); merged+=1
        else:
            c.execute('UPDATE customers SET guild_id=? WHERE id=?',(target,rid)); moved+=1
    return moved,merged

def _move_composite_config(c, table, keycol, source_guild, target):
    rows=c.execute(f'SELECT {qid(keycol)} FROM {qid(table)} WHERE guild_id=?',(source_guild,)).fetchall()
    moved=merged=0
    for (key,) in rows:
        exists=c.execute(f'SELECT 1 FROM {qid(table)} WHERE guild_id=? AND {qid(keycol)}=?',(target,key)).fetchone()
        if exists:
            # Target/canonical value wins. Legacy alias is discarded after being preserved in backup/report.
            c.execute(f'DELETE FROM {qid(table)} WHERE guild_id=? AND {qid(keycol)}=?',(source_guild,key)); merged+=1
        else:
            c.execute(f'UPDATE {qid(table)} SET guild_id=? WHERE guild_id=? AND {qid(keycol)}=?',(target,source_guild,key)); moved+=1
    return moved,merged

def repair_guild_scope(stage,report):
    target,source=primary_guild(stage); report['primary_guild_id']=target; report['primary_guild_source']=source
    c=sqlite3.connect(stage); ts=tables(c); changes={}; aliases={}
    if not target:
        c.close(); raise RuntimeError('Guild canônica não resolvida')
    # Inventory every non-canonical guild before changing anything.
    for t in sorted(ts):
        cols={x[1] for x in info(c,t)}
        if 'guild_id' not in cols: continue
        for g,n in c.execute(f'SELECT guild_id,COUNT(*) FROM {qid(t)} WHERE guild_id IS NOT NULL AND guild_id>0 AND guild_id<>? GROUP BY guild_id',(target,)):
            aliases.setdefault(str(g),{})[t]=int(n)
    # Repair all guild-scoped business/config records. Special tables need conflict-safe merging.
    for sg in sorted({int(x) for x in aliases}):
        if 'customers' in ts:
            moved,merged=_merge_customer_alias(c,sg,target)
            if moved or merged: changes.setdefault('customers',{'moved':0,'merged':0});changes['customers']['moved']+=moved;changes['customers']['merged']+=merged
        for t,key in (('guild_config','key'),('persistent_panels','panel_key'),('risk_rules','key')):
            if t in ts:
                moved,merged=_move_composite_config(c,t,key,sg,target)
                if moved or merged: changes.setdefault(t,{'moved':0,'merged':0});changes[t]['moved']+=moved;changes[t]['merged']+=merged
        for t in sorted(ts):
            if t in ('customers','guild_config','persistent_panels','risk_rules'): continue
            cols={x[1] for x in info(c,t)}
            if 'guild_id' not in cols: continue
            try:
                cur=c.execute(f'UPDATE {qid(t)} SET guild_id=? WHERE guild_id=?',(target,sg))
                if cur.rowcount: changes[t]=changes.get(t,0)+cur.rowcount
            except sqlite3.IntegrityError as e:
                # Never hide a collision; rollback the whole staged migration.
                c.rollback();c.close();raise RuntimeError(f'Conflito ao reparar guild em {t}: {e}')
    c.commit();c.close();report['guild_alias_inventory']=aliases;report['guild_scope_repairs']=changes
    print(f'[FORENSICS] Guild canônica: {target} ({source})')
    print(f'[FORENSICS] Guilds alias detectadas: {aliases or "nenhuma"}')
    print(f'[FORENSICS] Reparos de escopo: {changes or "nenhum"}')

def prepare():
    if MARKER.exists() and TARGET.exists():
        os.environ['DATABASE_URL']='sqlite:///'+str(TARGET).replace('\\','/')
        os.environ['CLUTCH_CANONICAL_DB']=str(TARGET)
        os.environ['CLUTCH_MIGRATION_REPORT']=str(REPORT)
        os.environ['CANONICAL_GUILD_ID']=str(DEFAULT_CANONICAL_GUILD_ID)
        os.environ['GUILD_ID']=str(DEFAULT_CANONICAL_GUILD_ID)
        print('[RECOVERY] Migração V3.4.5 já aplicada. Recovery histórico ignorado neste boot.')
        print(f'[DATA] Canonical DB: {TARGET}')
        print(f'[IDENTITY] Runtime guild canônica: {DEFAULT_CANONICAL_GUILD_ID}')
        return TARGET
    SHARED.mkdir(exist_ok=True)
    stage=SHARED/f'.clutch_v3_4_4_stage_{STAMP}.db';backup=None
    report={'version':VERSION,'started_at':datetime.now(timezone.utc).isoformat(),'status':'STARTED','inventory':[],'sources':[]}
    candidates=discover_sources(); valid=[]; detected=set()
    print(f'[RECOVERY] Inventariando {len(candidates)} banco(s) histórico(s)...')
    for p in candidates:
        r=inspect_db(p);report['inventory'].append(r)
        if r['valid']:
            r['guilds']=guild_inventory(p)
            valid.append(p);detected.update(r['order_codes']);detected.update(r['operation_order_codes'])
            print(f"[RECOVERY] OK {p} | orders={len(r['order_codes'])} | order_ops={len(r['operation_order_codes'])} | guilds={r['guilds']}")
        else: print(f"[RECOVERY] IGNORADO {p} | {r['error']}")
    report['detected_historical_order_codes']=sorted(detected)
    create_schema(stage)
    # Merge every valid legacy DB, then current canonical. No score winner.
    for p in valid:
        print(f'[RECOVERY] Consolidando: {p}')
        merge_source(p,stage,report)
    if TARGET.exists() and TARGET.stat().st_size>=4096:
        r=inspect_db(TARGET);report['canonical_before']=r
        if r['valid']:
            detected.update(r['order_codes']);detected.update(r['operation_order_codes']);merge_source(TARGET,stage,report)
    # Bootstrap Guard: never promote an empty/reduced staging DB over a canonical DB that
    # previously contained Clutch business/config data.
    before_tables=(report.get('canonical_before') or {}).get('tables',{})
    stage_c=sqlite3.connect(stage); stage_tables={t:count(stage_c,t) for t in tables(stage_c)}; stage_c.close()
    protected=('orders','operations_queue','customers','skins','negotiations','tradein_items','guild_config','persistent_panels')
    regress=[t for t in protected if int(before_tables.get(t,0) or 0)>0 and int(stage_tables.get(t,0) or 0)==0]
    if regress:
        report['status']='ABORTED_EMPTY_GUARD'; report['errors']=['Staging perdeu dados existentes: '+', '.join(regress)]
        REPORT.write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf-8'); stage.unlink(missing_ok=True)
        print('[RECOVERY] ABORTED: staging vazio/reduzido; banco canônico preservado.')
        print('[RECOVERY] Tabelas protegidas:', ', '.join(regress))
        raise RuntimeError('Bootstrap Guard bloqueou promoção destrutiva')
    repair_guild_scope(stage,report)
    reconcile_pipeline(stage,report)
    report['detected_historical_order_codes']=sorted(detected)
    ok,metrics,errors,missing=validate(stage,detected);report['after']=metrics;report['errors']=errors;report['missing_historical_orders']=missing
    if not ok:
        report['status']='ROLLED_BACK';REPORT.write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf-8');stage.unlink(missing_ok=True)
        print('[RECOVERY] FALHOU. Banco canônico anterior preservado.')
        for e in errors:print('[RECOVERY] ERRO:',e)
    else:
        if TARGET.exists():backup=SHARED/f'clutch_v2_pre_v3_4_4_{STAMP}.db';shutil.copy2(TARGET,backup)
        
        try:
            os.replace(stage,TARGET)
        except PermissionError as e:
            report['status']='BLOCKED_DB_IN_USE';report['errors']=[f'Banco em uso por outro processo: {e}'];REPORT.write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf-8')
            stage.unlink(missing_ok=True)
            print('[RECOVERY] BLOQUEADO: clutch_v2.db está em uso por outra versão/processo.')
            print('[RECOVERY] Feche todas as janelas antigas do Clutch OS e execute novamente.')
            raise RuntimeError('Banco canônico em uso; promoção cancelada com segurança') from e
        report['status']='COMMITTED';report['backup']=str(backup) if backup else None;report['completed_at']=datetime.now(timezone.utc).isoformat();REPORT.write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf-8')
        MARKER.write_text(json.dumps({'version':'3.4.5','canonical_guild_id':DEFAULT_CANONICAL_GUILD_ID,'completed_at':report['completed_at']},indent=2),encoding='utf-8')
        print('[RECOVERY] COMMIT OK. Histórico consolidado no banco canônico.')
        print(f'[RECOVERY] Encomendas históricas detectadas: {len(detected)} | Core final: {metrics.get("orders",0)} | reconstruídas de Operations: {len(report.get("reconstructed_orders",[]))}')
        if detected:print('[RECOVERY] ENC detectadas: '+', '.join(sorted(detected)))
        if backup:print(f'[RECOVERY] Backup pré-recuperação: {backup}')
    print(f'[DATA] Canonical DB: {TARGET}')
    os.environ['DATABASE_URL']='sqlite:///'+str(TARGET).replace('\\','/')
    os.environ['CLUTCH_CANONICAL_DB']=str(TARGET);os.environ['CLUTCH_MIGRATION_REPORT']=str(REPORT)
    # One identity for Bot/API/Web after recovery; stale legacy GUILD_ID cannot split runtime scope.
    os.environ['CANONICAL_GUILD_ID']=str(DEFAULT_CANONICAL_GUILD_ID)
    os.environ['GUILD_ID']=str(DEFAULT_CANONICAL_GUILD_ID)
    print(f'[IDENTITY] Runtime guild canônica: {DEFAULT_CANONICAL_GUILD_ID}')
    return TARGET

if __name__=='__main__':prepare()
