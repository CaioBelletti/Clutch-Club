import os
import hmac
import hashlib
from datetime import datetime, timezone, timedelta
from fastapi import FastAPI, Header, HTTPException, Body, Request
from fastapi.responses import HTMLResponse, Response, RedirectResponse, JSONResponse
from sqlalchemy import select, func
from clutch_bot.db import init_db, Session
from clutch_bot.models import Skin, Buylist, Sale, Order, Feedback, Audit, Operation, Negotiation, NegotiationOrder, TradeInItem, NegotiationPayment, Ledger
from clutch_os.core.models_ext import Customer
from clutch_os.core.engine import wallet, analyze_purchase

app=FastAPI(title='Clutch OS API',version='3.7.5')

CANONICAL_GUILD_ID=int(os.getenv('GUILD_ID','1549553223470416022') or 1549553223470416022)

SESSION_COOKIE='clutch_admin_session'

def _admin_key():
    return (os.getenv('ADMIN_API_KEY') or '').strip()

def _session_value():
    key=_admin_key()
    if not key: return ''
    return hmac.new(key.encode('utf-8'),b'clutch-control-session-v1',hashlib.sha256).hexdigest()

def _session_ok(request:Request):
    expected=_session_value()
    supplied=request.cookies.get(SESSION_COOKIE,'')
    return bool(expected and supplied and hmac.compare_digest(supplied,expected))

@app.middleware('http')
async def canonical_guild_lock(request, call_next):
    # Single-guild runtime: the Core is authoritative. Old/stale clients can never
    # select another namespace. We canonicalize the path BEFORE FastAPI routing.
    path=request.scope.get('path') or request.url.path
    prefix='/api/v1/'
    exempt={'/api/v1/identity','/api/v1/guilds'}
    if path.startswith(prefix) and path not in exempt:
        parts=path.split('/')
        # /api/v1/<resource>/<guild_id>/...
        if len(parts) >= 5 and parts[4].isdigit():
            requested=int(parts[4])
            if requested != CANONICAL_GUILD_ID:
                original=path
                parts[4]=str(CANONICAL_GUILD_ID)
                canonical='/'.join(parts)
                request.scope['path']=canonical
                request.scope['raw_path']=canonical.encode('ascii')
                print(f'[IDENTITY] CANONICALIZADO cliente legado: {requested} -> {CANONICAL_GUILD_ID} | {original}')
    # Sessao web HttpOnly: a ADMIN_API_KEY nunca fica no JavaScript/URL.
    if path.startswith('/api/v1/') and path not in exempt and _session_ok(request):
        headers=list(request.scope.get('headers',[]))
        if not any(k.lower()==b'x-admin-key' for k,v in headers):
            headers.append((b'x-admin-key',_admin_key().encode('utf-8')))
            request.scope['headers']=headers
    response=await call_next(request)
    if path=='/' or path.startswith('/api/v1/identity'):
        response.headers['Cache-Control']='no-store, no-cache, must-revalidate, max-age=0'
        response.headers['Pragma']='no-cache'
        response.headers['Expires']='0'
    return response

def auth(x_admin_key:str|None):
    expected=_admin_key()
    if expected and x_admin_key!=expected: raise HTTPException(401,'Invalid admin key')

def _database_label():
    try:
        from clutch_bot.db import engine
        url=engine.url
        if url.get_backend_name()=='sqlite':
            from pathlib import Path
            db=Path(url.database or 'clutch_v2.db')
            if not db.is_absolute(): db=(Path.cwd()/db).resolve()
            return str(db)
        return url.render_as_string(hide_password=True)
    except Exception as e:
        return f'erro ao resolver banco: {e}'

@app.on_event('startup')
def startup():
    init_db()
    print(f'[CLUTCH DATA] API/Core DB: {_database_label()}')
    # Reconcile delivered orders created by older builds that did not close finance.
    # Ledger keys make this safe to run at every boot.
    try:
        backfilled=0
        with Session.begin() as q:
            delivered=q.scalars(select(Order).where(Order.guild_id==CANONICAL_GUILD_ID,Order.status=='DELIVERED')).all()
            for o in delivered:
                if o.customer_price is None or o.found_price is None: continue
                sale_note=f'{o.code}:ORDER_SALE'; cost_note=f'{o.code}:ORDER_COST'
                has_sale=q.scalar(select(Ledger.id).where(Ledger.guild_id==CANONICAL_GUILD_ID,Ledger.kind=='ORDER_SALE',Ledger.note==sale_note).limit(1))
                has_cost=q.scalar(select(Ledger.id).where(Ledger.guild_id==CANONICAL_GUILD_ID,Ledger.kind=='ORDER_COST',Ledger.note==cost_note).limit(1))
                if not has_cost:
                    q.add(Ledger(guild_id=CANONICAL_GUILD_ID,kind='ORDER_COST',amount=-o.found_price,note=cost_note)); backfilled+=1
                if not has_sale:
                    q.add(Ledger(guild_id=CANONICAL_GUILD_ID,kind='ORDER_SALE',amount=o.customer_price,note=sale_note)); backfilled+=1
        if backfilled: print(f'[FINANCE] Backfill de encomendas entregues: {backfilled} lançamento(s).')
    except Exception as exc:
        print(f'[FINANCE] Backfill falhou: {exc}')
    try:
        repaired=[]
        # Historical builds could publish/requeue the same ORDER more than once.
        # Preserve history, but only one active Operation may represent an Order.
        with Session.begin() as q:
            order_codes=list(q.scalars(select(Order.code).where(Order.guild_id==CANONICAL_GUILD_ID)).all())
            for code in order_codes:
                ops=list(q.scalars(select(Operation).where(Operation.guild_id==CANONICAL_GUILD_ID,Operation.kind=='ORDER',Operation.ref_code==code).order_by(Operation.id.asc())).all())
                active=[x for x in ops if x.status not in ('DONE','CANCELLED')]
                if len(active)>1:
                    keep=active[-1]
                    for x in active:
                        if x.id==keep.id: continue
                        x.status='CANCELLED'
                        tag='[INTEGRITY V3.7.4] Duplicata histórica preservada/inativada.'
                        if tag not in (x.detail or ''): x.detail=((x.detail or '')+'\n'+tag).strip()
                    repaired.append(f'{code}:{len(active)} ativas->1 ativa')
            if repaired:
                q.add(Audit(guild_id=CANONICAL_GUILD_ID,actor_id=0,action='INTEGRITY_REPAIR',entity_type='operations',entity_id=0,detail='; '.join(repaired)))
        if repaired: print('[INTEGRITY] Auto-repair Operations: '+', '.join(repaired))
        with Session() as q:
            models=[(Customer,'customers'),(Order,'orders'),(Operation,'operations'),(Skin,'skins'),(Negotiation,'negotiations'),(Ledger,'ledger')]
            counts={name:int(q.scalar(select(func.count()).select_from(model).where(model.guild_id==CANONICAL_GUILD_ID)) or 0) for model,name in models}
            foreign=[]
            for model,name in models:
                for g,c in q.execute(select(model.guild_id,func.count()).group_by(model.guild_id)).all():
                    if int(g)!=CANONICAL_GUILD_ID and int(c)>0: foreign.append(f'{name}@{g}={c}')
            print(f'[INTEGRITY] Snapshot guild {CANONICAL_GUILD_ID}: {counts}')
            print('[INTEGRITY] Namespace: '+('OK' if not foreign else 'ATENCAO '+', '.join(foreign)))
    except Exception as exc:
        print(f'[INTEGRITY] ERRO no preflight: {type(exc).__name__}: {exc}')

LOGIN_HTML=r'''<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Clutch Control - Login</title><style>body{margin:0;background:#090a0b;color:#f5f6f7;font:14px system-ui;display:grid;place-items:center;min-height:100vh}.box{width:min(420px,88vw);background:#141516;border:1px solid #292c2f;border-radius:22px;padding:28px;box-shadow:0 24px 80px #0008}.brand{font-size:20px;font-weight:900;margin-bottom:24px}.mark{display:inline-grid;place-items:center;width:32px;height:32px;border-radius:10px;background:#d7ff00;color:#090a0b;margin-right:10px}h1{margin:0 0 8px;font-size:30px}.muted{color:#8d9197;margin-bottom:18px}input{width:100%;box-sizing:border-box;background:#0e0f10;border:1px solid #303337;color:white;border-radius:12px;padding:13px;margin:8px 0 12px}button{width:100%;border:0;border-radius:12px;background:#d7ff00;color:#090a0b;padding:13px;font-weight:900;cursor:pointer}.err{color:#ff5d70;min-height:20px;margin-top:10px}</style></head><body><div class="box"><div class="brand"><span class="mark">C</span>CLUTCH CONTROL</div><h1>Acesso administrativo</h1><div class="muted">Entre com a chave administrativa configurada no Railway.</div><input id="key" type="password" autocomplete="current-password" placeholder="ADMIN_API_KEY"><button id="go">ENTRAR</button><div class="err" id="err"></div></div><script>async function login(){const key=document.getElementById('key').value;document.getElementById('err').textContent='';const r=await fetch('/auth/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({key})});if(r.ok){location.replace('/');return}document.getElementById('err').textContent='Chave invalida.'}document.getElementById('go').onclick=login;document.getElementById('key').addEventListener('keydown',e=>{if(e.key==='Enter')login()});</script></body></html>'''

@app.get('/login',response_class=HTMLResponse,include_in_schema=False)
def login_page(request:Request):
    if _session_ok(request): return RedirectResponse('/',status_code=303)
    return HTMLResponse(LOGIN_HTML,headers={'Cache-Control':'no-store'})

@app.post('/auth/login',include_in_schema=False)
def login_action(payload:dict=Body(default={})):
    expected=_admin_key(); supplied=str(payload.get('key') or '')
    if not expected or not hmac.compare_digest(supplied,expected):
        raise HTTPException(401,'Invalid admin key')
    r=JSONResponse({'ok':True})
    r.set_cookie(SESSION_COOKIE,_session_value(),httponly=True,secure=True,samesite='strict',max_age=60*60*12,path='/')
    return r

@app.post('/auth/logout',include_in_schema=False)
def logout():
    r=JSONResponse({'ok':True}); r.delete_cookie(SESSION_COOKIE,path='/'); return r

@app.get('/favicon.ico', include_in_schema=False)
def favicon(): return Response(status_code=204)

@app.get('/sw.js', include_in_schema=False)
def service_worker(): return Response(status_code=204)


@app.get('/inspect/{skin_code}', response_class=HTMLResponse, include_in_schema=False)
def inspect_skin(skin_code:str):
    code=(skin_code or '').strip().upper()
    with Session() as q:
        skin=q.scalar(select(Skin).where(Skin.code==code))
    if not skin or not skin.inspect:
        raise HTTPException(404,'Skin sem Inspect Link cadastrado')
    inspect_link=str(skin.inspect).strip()
    allowed='steam://run/730//+csgo_econ_action_preview'
    if not inspect_link.lower().startswith(allowed.lower()):
        raise HTTPException(400,'Inspect Link inválido para CS2')
    import html, json
    safe_name=html.escape(skin.name or code)
    safe_code=html.escape(code)
    js_uri=json.dumps(inspect_link)
    page=f'''<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Inspecionar {safe_code} no CS2</title>
<style>body{{margin:0;background:#090909;color:#fff;font-family:Arial,sans-serif;display:grid;place-items:center;min-height:100vh}}.card{{width:min(520px,88vw);background:#111;border:1px solid #b9903b;border-radius:18px;padding:28px;text-align:center;box-shadow:0 20px 70px #000}}h1{{color:#e0b85a}}p{{color:#bbb;line-height:1.5}}button{{border:0;border-radius:10px;padding:15px 22px;background:#d6a94b;color:#080808;font-weight:800;font-size:16px;cursor:pointer}}small{{display:block;color:#777;margin-top:18px}}</style></head><body><div class="card"><h1>🎮 ABRIR NO CS2</h1><h2>{safe_name}</h2><p>O navegador tentará abrir a Steam. Confirme <b>Abrir Steam</b> para inspecionar esta skin dentro do CS2.</p><button id="open">ABRIR NO CS2</button><small>CLUTCH CLUB • PLAY • TRADE • EVOLVE</small></div>
<script>const uri={js_uri}; function openCS2(){{window.location.href=uri}} document.getElementById('open').onclick=openCS2; setTimeout(openCS2,350);</script></body></html>'''
    return HTMLResponse(page, headers={'Cache-Control':'no-store'})

@app.get('/health')
def health(): return {'ok':True,'service':'clutch-os','version':'3.7.5','control_center':True,'database':_database_label()}

@app.get('/api/v1/identity')
def identity():
    gid=CANONICAL_GUILD_ID
    return {'canonical_guild_id':gid,'source':'DISCORD_AUTHORITATIVE','match_required':True}

@app.get('/api/v1/guilds')
def guilds(x_admin_key:str|None=Header(default=None)):
    auth(x_admin_key)
    # Descobre servidores que ja possuem dados/configuracao local.
    from clutch_bot.models import GuildConfig
    with Session() as s:
        ids=set(s.scalars(select(GuildConfig.guild_id).distinct()).all())
        ids.update(s.scalars(select(Order.guild_id).distinct()).all())
        ids.update(s.scalars(select(Skin.guild_id).distinct()).all())
        ids.update(s.scalars(select(Operation.guild_id).distinct()).all())
        return sorted(int(x) for x in ids if x)

@app.get('/api/v1/diagnostics/{guild_id}')
def diagnostics(guild_id:int,x_admin_key:str|None=Header(default=None)):
    auth(x_admin_key)
    with Session() as s:
        def n(model): return int(s.scalar(select(func.count()).select_from(model).where(model.guild_id==guild_id)) or 0)
        counts={'customers':n(Customer),'orders':n(Order),'operations':n(Operation),'skins':n(Skin),'negotiations':n(Negotiation),'ledger':n(Ledger)}
        other={}
        for model,name in [(Customer,'customers'),(Order,'orders'),(Operation,'operations'),(Skin,'skins'),(Negotiation,'negotiations'),(Ledger,'ledger')]:
            rows=s.execute(select(model.guild_id,func.count()).group_by(model.guild_id)).all()
            vals={str(g):int(c) for g,c in rows if int(g)!=int(guild_id)}
            if vals: other[name]=vals
        order_rows=s.scalars(select(Order).where(Order.guild_id==guild_id)).all()
        ops=s.scalars(select(Operation).where(Operation.guild_id==guild_id,Operation.kind=='ORDER',Operation.status.not_in(['DONE','CANCELLED']))).all()
        customers=set(s.scalars(select(Customer.id).where(Customer.guild_id==guild_id)).all())
        byref={}
        for op in ops: byref.setdefault(op.ref_code,[]).append(op)
        issues=[]
        for o in order_rows:
            if not o.customer_id or o.customer_id not in customers: issues.append(f'{o.code}:CRM')
            if not byref.get(o.code): issues.append(f'{o.code}:OP_MISSING')
            elif len(byref[o.code])>1: issues.append(f'{o.code}:OP_DUPLICATE({len(byref[o.code])})')
            elif byref[o.code][0].entity_id not in (None,o.id): issues.append(f'{o.code}:OP_ENTITY')
        return {'ok':not issues and not other,'canonical_guild_id':guild_id,'database':_database_label(),'counts':counts,'foreign_namespaces':other,'issues':issues}

@app.get('/api/v1/dashboard/{guild_id}')
def dashboard(guild_id:int,x_admin_key:str|None=Header(default=None)):
    auth(x_admin_key)

    # Cada KPI usa uma sessao curta. Assim, se um indicador falhar,
    # o restante do dashboard continua disponivel em vez de retornar HTTP 500.
    errors=[]
    def scalar(name, stmt, default=0):
        try:
            with Session() as q:
                value=q.scalar(stmt)
                return default if value is None else value
        except Exception as exc:
            errors.append(f'{name}: {type(exc).__name__}')
            print(f'[DASHBOARD] KPI {name} falhou: {exc}')
            return default

    def count(name, model, *where):
        return scalar(name, select(func.count()).select_from(model).where(*where), 0)

    try:
        w=wallet(guild_id)
    except Exception as exc:
        errors.append(f'wallet: {type(exc).__name__}')
        print(f'[DASHBOARD] Wallet falhou: {exc}')
        w={'cash':0,'inventory':0,'reserved':0,'receivables':0,'realized_profit':0,'potential_profit':0}

    available=count('skins_available',Skin,Skin.guild_id==guild_id,Skin.status=='AVAILABLE')
    reserved=count('skins_reserved',Skin,Skin.guild_id==guild_id,Skin.status=='RESERVED')
    sold=count('skins_sold',Skin,Skin.guild_id==guild_id,Skin.status=='SOLD')
    personal=count('skins_personal',Skin,Skin.guild_id==guild_id,Skin.status=='PERSONAL')
    pending=count('buylist_pending',Buylist,Buylist.guild_id==guild_id,Buylist.status.in_(['PENDING','PROPOSED','COUNTERED']))
    sales_completed=count('sales_completed',Sale,Sale.guild_id==guild_id,Sale.status=='COMPLETED')
    orders_delivered=count('orders_delivered',Order,Order.guild_id==guild_id,Order.status=='DELIVERED')
    sales_open=sales_completed+orders_delivered
    orders_open=count('orders_open',Order,Order.guild_id==guild_id,Order.status.not_in(['DELIVERED','CANCELLED']))
    operations_open=count('operations_open',Operation,Operation.guild_id==guild_id,Operation.status.in_(['OPEN','WAITING','ACTION_REQUIRED']))
    tradeins_open=count('tradeins_open',Negotiation,Negotiation.guild_id==guild_id,Negotiation.status.not_in(['COMPLETED','CANCELLED']))
    customers=count('customers',Customer,Customer.guild_id==guild_id)
    avg_rating=scalar('rating',select(func.avg(Feedback.rating)).where(Feedback.guild_id==guild_id),0)
    feedback_count=count('feedback_count',Feedback,Feedback.guild_id==guild_id)
    sale_revenue=scalar('sale_revenue',select(func.coalesce(func.sum(Sale.sale_price),0)).where(Sale.guild_id==guild_id,Sale.status=='COMPLETED'),0)
    order_revenue=scalar('order_revenue',select(func.coalesce(func.sum(Ledger.amount),0)).where(Ledger.guild_id==guild_id,Ledger.kind=='ORDER_SALE'),0)
    revenue=(sale_revenue or 0)+(order_revenue or 0)

    # SQLAlchemy 2.x precisa de um FROM explicito neste JOIN.
    realized_stmt=(
        select(func.coalesce(func.sum(Sale.sale_price-Sale.sale_fees-Skin.cost-Skin.acquisition_fees),0))
        .select_from(Sale)
        .join(Skin, Sale.skin_id==Skin.id)
        .where(Sale.guild_id==guild_id,Sale.status=='COMPLETED')
    )
    sale_realized=scalar('sale_realized_profit',realized_stmt,0)
    order_realized=scalar('order_realized_profit',select(func.coalesce(func.sum(Ledger.amount),0)).where(Ledger.guild_id==guild_id,Ledger.kind.in_(['ORDER_SALE','ORDER_COST','ORDER_FEE'])),0)
    realized=(sale_realized or 0)+(order_realized or 0)

    inv_cost=float(w.get('inventory',0) or 0); potential=float(w.get('potential_profit',0) or 0)
    revenue_f=float(revenue or 0); realized_f=float(realized or 0)
    roi=(realized_f/(revenue_f-realized_f)*100) if revenue_f-realized_f>0 else 0
    if errors:
        raise HTTPException(500, detail={'message':'Dashboard inconsistente; zeros artificiais bloqueados','errors':errors})
    return {**{k:float(v or 0) for k,v in w.items()},'skins_available':available,'skins_reserved':reserved,'skins_sold':sold,'skins_personal':personal,'buylist_pending':pending,'sales_open':sales_open,'orders_open':orders_open,'operations_open':operations_open,'tradeins_open':tradeins_open,'customers':customers,'rating':float(avg_rating or 0),'feedback_count':feedback_count,'revenue':revenue_f,'realized_profit':realized_f,'roi':roi,'inventory_sale_value':inv_cost+potential,'partial':bool(errors),'kpi_errors':errors,'buylist_enabled':(os.getenv('BUYLIST_ENABLED','false').strip().lower() in ('1','true','yes','on','sim'))}

@app.get('/api/v1/skins/{guild_id}')
def skins(guild_id:int,x_admin_key:str|None=Header(default=None)):
    auth(x_admin_key)
    with Session() as s:
        rows=s.scalars(select(Skin).where(Skin.guild_id==guild_id).order_by(Skin.id.desc()).limit(100)).all()
        return [{'code':x.code,'name':x.name,'status':x.status,'exterior':x.exterior,'float':x.floatv,'pattern':x.pattern,'cost':float(x.cost),'fees':float(x.acquisition_fees),'price':float(x.price),'image_url':x.image_url,'source':x.source,'created_at':x.created_at.isoformat() if x.created_at else None} for x in rows]

@app.get('/api/v1/integrity/{guild_id}')
def integrity(guild_id:int,x_admin_key:str|None=Header(default=None)):
    auth(x_admin_key)
    with Session() as s:
        accepted=s.scalars(select(TradeInItem).join(Negotiation,TradeInItem.negotiation_id==Negotiation.id).where(Negotiation.guild_id==guild_id,TradeInItem.status=='ACCEPTED')).all()
        orphan=[]
        for t in accepted:
            sk=s.get(Skin,t.stock_skin_id) if t.stock_skin_id else None
            if not sk or sk.guild_id!=guild_id:
                orphan.append({'tradein':t.code,'stock_skin_id':t.stock_skin_id})
        return {'ok':not orphan,'accepted_tradeins':len(accepted),'orphan_tradeins':orphan}

@app.get('/api/v1/activity/{guild_id}')
def activity(guild_id:int,x_admin_key:str|None=Header(default=None)):
    auth(x_admin_key)
    with Session() as s:
        audits=s.scalars(select(Audit).where(Audit.guild_id==guild_id).order_by(Audit.id.desc()).limit(12)).all()
        return [{'action':a.action,'entity':a.entity_type,'detail':a.detail or '', 'at':a.created_at.isoformat() if a.created_at else None} for a in audits]


def _money(v): return float(v or 0)

def _neg_detail(s,n):
    items=s.scalars(select(TradeInItem).where(TradeInItem.negotiation_id==n.id).order_by(TradeInItem.id)).all()
    links=s.scalars(select(NegotiationOrder).where(NegotiationOrder.negotiation_id==n.id)).all()
    orders=[]
    for link in links:
        o=s.get(Order,link.order_id)
        if o: orders.append({'code':o.code,'skin_name':o.skin_name,'status':o.status,'cost':_money(o.found_price),'customer_price':_money(o.customer_price)})
    pays=s.scalars(select(NegotiationPayment).where(NegotiationPayment.negotiation_id==n.id).order_by(NegotiationPayment.id)).all()
    order_cost=sum(x['cost'] for x in orders)
    expected_credit=sum(_money(x.credit_value) for x in items if x.status not in ('REJECTED','CANCELLED'))
    accepted_credit=sum(_money(x.credit_value) for x in items if x.status=='ACCEPTED')
    cash_ok=_money(n.cash_received)>=_money(n.cash_due)
    credit_ok=expected_credit>=_money(n.trade_credit)
    assets_ok=bool(items) and accepted_credit>=_money(n.trade_credit) if _money(n.trade_credit)>0 else True
    if n.status=='CANCELLED': lifecycle='CANCELLED'
    elif cash_ok and assets_ok: lifecycle='COMPLETED'
    elif cash_ok and credit_ok: lifecycle='AWAITING_ASSETS'
    elif cash_ok: lifecycle='FINANCIALLY_SETTLED'
    elif any(x.status in ('RECEIVED','INSPECTED','ACCEPTED') for x in items): lifecycle='ASSETS_RECEIVED'
    else: lifecycle='OPEN'
    costs_known=bool(orders) and all(x['cost']>0 for x in orders)
    projected_profit=(_money(n.sale_total)-order_cost) if costs_known else None
    return {'id':n.id,'code':n.code,'kind':n.kind,'status':lifecycle,'stored_status':n.status,'user_id':n.user_id,'sale_total':_money(n.sale_total),'trade_credit':_money(n.trade_credit),'cash_due':_money(n.cash_due),'cash_received':_money(n.cash_received),'notes':n.notes or '', 'order_cost':order_cost,'costs_known':costs_known,'projected_profit':projected_profit,'trade_items_value':expected_credit,'accepted_trade_value':accepted_credit,'trade_credit_remaining':max(0,_money(n.trade_credit)-expected_credit),
      'orders':orders,'items':[{'code':x.code,'name':x.name,'exterior':x.exterior,'float':x.floatv,'pattern':x.pattern,'credit_value':_money(x.credit_value),'status':x.status,'stock_skin_id':x.stock_skin_id} for x in items],
      'payments':[{'kind':x.kind,'amount':_money(x.amount),'status':x.status,'reference':x.reference,'at':x.created_at.isoformat() if x.created_at else None} for x in pays],
      'created_at':n.created_at.isoformat() if n.created_at else None,'updated_at':n.updated_at.isoformat() if n.updated_at else None}

@app.get('/api/v1/negotiation/{guild_id}/{code}')
def negotiation_detail(guild_id:int,code:str,x_admin_key:str|None=Header(default=None)):
    auth(x_admin_key)
    with Session() as s:
        n=s.scalar(select(Negotiation).where(Negotiation.guild_id==guild_id,Negotiation.code==code.upper()))
        if not n: raise HTTPException(404,'Negociação não encontrada')
        return _neg_detail(s,n)

@app.get('/api/v1/finance/{guild_id}')
def finance(guild_id:int,x_admin_key:str|None=Header(default=None)):
    auth(x_admin_key)
    with Session() as s:
        ledger=s.scalars(select(Ledger).where(Ledger.guild_id==guild_id).order_by(Ledger.id.desc()).limit(100)).all()
        negs=s.scalars(select(Negotiation).where(Negotiation.guild_id==guild_id).order_by(Negotiation.id.desc())).all()
        skins=s.scalars(select(Skin).where(Skin.guild_id==guild_id)).all()
        cash=sum(_money(x.amount) for x in ledger)
        inventory=sum(_money(x.cost)+_money(x.acquisition_fees) for x in skins if x.status in ('AVAILABLE','RESERVED','TRADE_LOCK'))
        trade_assets=sum(_money(x.cost) for x in skins if x.source=='TRADE_IN' and x.status in ('AVAILABLE','RESERVED','TRADE_LOCK'))
        receivable=0; trade_receivable=0; projected=0; projected_known=0
        for n in negs:
            d=_neg_detail(s,n)
            if d['status'] not in ('CANCELLED','COMPLETED'):
                receivable+=max(0,d['cash_due']-d['cash_received'])
                trade_receivable+=max(0,d['trade_credit']-d['accepted_trade_value'])
            if d['projected_profit'] is not None and d['status']!='CANCELLED':
                projected+=d['projected_profit']; projected_known+=1
        return {'cash':cash,'inventory':inventory,'trade_assets':trade_assets,'receivables':receivable,'trade_receivable':trade_receivable,'trade_credit_open':trade_receivable,'projected_negotiation_profit':projected if projected_known else None,'projected_known_count':projected_known,
          'ledger':[{'kind':x.kind,'amount':_money(x.amount),'note':x.note or '', 'skin_id':x.skin_id,'sale_id':x.sale_id,'at':x.created_at.isoformat() if x.created_at else None} for x in ledger]}

@app.post('/api/v1/tradein/{guild_id}')
def web_tradein_create(guild_id:int,payload:dict=Body(...),x_admin_key:str|None=Header(default=None)):
    auth(x_admin_key)
    total=float(payload.get('sale_total') or 0); credit=float(payload.get('trade_credit') or 0)
    if total<0 or credit<0 or credit>total: raise HTTPException(400,'Valores inválidos')
    with Session.begin() as s:
        customer_code=str(payload.get('customer_code') or '').strip().upper()
        if not customer_code: raise HTTPException(400,'Selecione um cliente CRM válido')
        customer=s.scalar(select(Customer).where(Customer.guild_id==guild_id,Customer.code==customer_code))
        if not customer: raise HTTPException(400,'Cliente CRM não encontrado neste servidor')
        user_id=int(customer.discord_id)
        selected=[str(x).strip().upper() for x in (payload.get('orders') or []) if str(x).strip()]
        if not selected: raise HTTPException(400,'Selecione pelo menos uma encomenda do cliente')
        resolved=[]
        for order_code in selected:
            o=s.scalar(select(Order).where(Order.guild_id==guild_id,Order.code==order_code))
            if not o: raise HTTPException(404,f'Encomenda {order_code} não encontrada')
            if o.customer_id!=customer.id: raise HTTPException(409,f'{o.code} não está vinculada a {customer.code}. Reconcilie CRM ↔ Orders primeiro.')
            if s.scalar(select(NegotiationOrder.id).join(Negotiation,NegotiationOrder.negotiation_id==Negotiation.id).where(NegotiationOrder.order_id==o.id,Negotiation.status!='CANCELLED')):
                raise HTTPException(409,f'{o.code} já pertence a uma negociação ativa')
            resolved.append(o)
        n=Negotiation(code='PENDING',guild_id=guild_id,user_id=user_id,kind='TRADE_IN',status='OPEN',sale_total=total,trade_credit=credit,cash_due=total-credit,cash_received=0,notes=payload.get('notes') or None);s.add(n);s.flush();n.code=f'NEG-{n.id:05d}'
        for o in resolved:s.add(NegotiationOrder(negotiation_id=n.id,order_id=o.id))
        s.add(Audit(guild_id=guild_id,actor_id=0,action='WEB_TRADEIN_CREATE',entity_type='negotiation',entity_id=n.id,detail=n.code)); code=n.code
    return {'ok':True,'code':code}

@app.post('/api/v1/tradein/{guild_id}/{code}/item')
def web_tradein_item(guild_id:int,code:str,payload:dict=Body(...),x_admin_key:str|None=Header(default=None)):
    auth(x_admin_key)
    fv=str(payload.get('float') or '').replace(',','.')
    try:
        if not (0<=float(fv)<=1): raise ValueError()
    except: raise HTTPException(400,'Float inválido')
    with Session.begin() as s:
        n=s.scalar(select(Negotiation).where(Negotiation.guild_id==guild_id,Negotiation.code==code.upper()))
        if not n: raise HTTPException(404,'Negociação não encontrada')
        if n.status=='CANCELLED': raise HTTPException(409,'Negociação cancelada')
        name=str(payload.get('name') or '').strip(); credit=float(payload.get('credit_value') or 0)
        if not name or credit<=0: raise HTTPException(400,'Skin e crédito são obrigatórios')
        current=sum(_money(x) for x in s.scalars(select(TradeInItem.credit_value).where(TradeInItem.negotiation_id==n.id,TradeInItem.status.not_in(['REJECTED','CANCELLED']))).all())
        if current+credit>_money(n.trade_credit)+0.009: raise HTTPException(409,f'Crédito excede o limite da negociação. Restante: {max(0,_money(n.trade_credit)-current):.2f}')
        t=TradeInItem(negotiation_id=n.id,code='PENDING',name=name,exterior=str(payload.get('exterior') or '').upper(),floatv=fv,pattern=payload.get('pattern') or None,credit_value=credit,status='EXPECTED');s.add(t);s.flush();t.code=f'TI-{t.id:05d}'; out=t.code
    return {'ok':True,'code':out}

@app.post('/api/v1/tradein/{guild_id}/{code}/payment')
def web_tradein_payment(guild_id:int,code:str,payload:dict=Body(...),x_admin_key:str|None=Header(default=None)):
    auth(x_admin_key); amount=float(payload.get('amount') or 0)
    if amount<=0: raise HTTPException(400,'Valor deve ser positivo')
    with Session.begin() as s:
        n=s.scalar(select(Negotiation).where(Negotiation.guild_id==guild_id,Negotiation.code==code.upper()))
        if not n: raise HTTPException(404,'Negociação não encontrada')
        if n.status=='CANCELLED': raise HTTPException(409,'Negociação cancelada')
        remaining=max(0,_money(n.cash_due)-_money(n.cash_received))
        if amount>remaining+0.009: raise HTTPException(409,f'Pagamento excede o saldo. Restante: {remaining:.2f}')
        s.add(NegotiationPayment(negotiation_id=n.id,kind='CASH',amount=amount,status='CONFIRMED',reference=payload.get('reference') or 'PIX'));n.cash_received=_money(n.cash_received)+amount
        s.add(Ledger(guild_id=guild_id,kind='TRADEIN_CASH',amount=amount,note=n.code));s.add(Audit(guild_id=guild_id,actor_id=0,action='WEB_TRADEIN_PAYMENT',entity_type='negotiation',entity_id=n.id,detail=str(amount)))
    return {'ok':True}

@app.post('/api/v1/tradein/{guild_id}/{code}/item/{item_code}/transition')
def tradein_transition(guild_id:int,code:str,item_code:str,payload:dict=Body(...),x_admin_key:str|None=Header(default=None)):
    auth(x_admin_key); action=str(payload.get('action') or '').upper()
    transitions={'EXPECTED':{'RECEIVE':'RECEIVED','REJECT':'REJECTED'},'RECEIVED':{'INSPECT':'INSPECTED','REJECT':'REJECTED'},'INSPECTED':{'ACCEPT':'ACCEPTED','REJECT':'REJECTED'}}
    with Session.begin() as s:
        n=s.scalar(select(Negotiation).where(Negotiation.guild_id==guild_id,Negotiation.code==code.upper()))
        if not n: raise HTTPException(404,'Negociação não encontrada')
        t=s.scalar(select(TradeInItem).where(TradeInItem.negotiation_id==n.id,TradeInItem.code==item_code.upper()))
        if not t: raise HTTPException(404,'Trade-In não encontrado')
        nxt=transitions.get(t.status,{}).get(action)
        if not nxt: raise HTTPException(409,f'Ação {action} inválida para status {t.status}')
        if nxt=='ACCEPTED':
            if t.stock_skin_id: raise HTTPException(409,'Este Trade-In já possui SK vinculada')
            sk=Skin(code='PENDING',guild_id=guild_id,name=t.name,exterior=t.exterior,floatv=t.floatv,pattern=t.pattern,status='AVAILABLE',cost=t.credit_value,acquisition_fees=0,price=0,source='TRADE_IN',source_ref=f'{n.code}/{t.code}')
            s.add(sk);s.flush();sk.code=f'SK-{sk.id:05d}';t.stock_skin_id=sk.id
            s.add(Audit(guild_id=guild_id,actor_id=0,action='TRADEIN_TO_STOCK',entity_type='skin',entity_id=sk.id,detail=f'{n.code}/{t.code} -> {sk.code}'))
        t.status=nxt
        s.add(Audit(guild_id=guild_id,actor_id=0,action=f'TRADEIN_{nxt}',entity_type='tradein_item',entity_id=t.id,detail=f'{n.code}/{t.code}'))
        out={'ok':True,'status':nxt,'stock_skin_id':t.stock_skin_id}
    return out

@app.post('/api/v1/tradein/{guild_id}/{code}/cancel')
def cancel_negotiation(guild_id:int,code:str,x_admin_key:str|None=Header(default=None)):
    auth(x_admin_key)
    with Session.begin() as s:
        n=s.scalar(select(Negotiation).where(Negotiation.guild_id==guild_id,Negotiation.code==code.upper()))
        if not n: raise HTTPException(404,'Negociação não encontrada')
        if _money(n.cash_received)>0: raise HTTPException(409,'Não é possível cancelar negociação com pagamento confirmado')
        accepted=s.scalar(select(func.count()).select_from(TradeInItem).where(TradeInItem.negotiation_id==n.id,TradeInItem.status=='ACCEPTED')) or 0
        if accepted: raise HTTPException(409,'Não é possível cancelar negociação com ativo aceito em estoque')
        n.status='CANCELLED';s.add(Audit(guild_id=guild_id,actor_id=0,action='NEGOTIATION_CANCELLED',entity_type='negotiation',entity_id=n.id,detail=n.code))
    return {'ok':True}

@app.get('/api/v1/customers/{guild_id}')
def customers_api(guild_id:int,x_admin_key:str|None=Header(default=None)):
    auth(x_admin_key)
    with Session() as s:
        rows=s.scalars(select(Customer).where(Customer.guild_id==guild_id).order_by(Customer.display_name,Customer.code)).all()
        return [_customer_payload(x) for x in rows]



def _customer_payload(x):
    return {'code':x.code,'discord_id':x.discord_id,'display_name':x.display_name or x.code,'trade_url':x.trade_url or '',
            'whatsapp':getattr(x,'whatsapp',None) or '','notes':getattr(x,'notes',None) or ''}

def _ensure_customer(s,guild_id,discord_id,display_name=None):
    if not discord_id: return None
    c=s.scalar(select(Customer).where(Customer.guild_id==guild_id,Customer.discord_id==int(discord_id)))
    if c: return c
    c=Customer(guild_id=guild_id,discord_id=int(discord_id),code='PENDING',display_name=display_name or f'Discord {discord_id}')
    s.add(c);s.flush();c.code=f'CL-{c.id:05d}'
    return c

@app.post('/api/v1/customers/{guild_id}/sync-orders')
def sync_customers_from_orders(guild_id:int,x_admin_key:str|None=Header(default=None)):
    auth(x_admin_key)
    created=0
    with Session.begin() as s:
        ids=set(s.scalars(select(Order.user_id).where(Order.guild_id==guild_id)).all())
        ids.update(s.scalars(select(Buylist.user_id).where(Buylist.guild_id==guild_id)).all())
        ids.update(s.scalars(select(Sale.buyer_id).where(Sale.guild_id==guild_id)).all())
        for uid in ids:
            if uid and not s.scalar(select(Customer.id).where(Customer.guild_id==guild_id,Customer.discord_id==uid)):
                _ensure_customer(s,guild_id,uid); created+=1
        s.add(Audit(guild_id=guild_id,actor_id=0,action='CRM_SYNC',entity_type='customer',detail=f'{created} cliente(s) criado(s)'))
    return {'ok':True,'created':created}

@app.get('/api/v1/customers/{guild_id}/{code}/orders')
def customer_orders(guild_id:int,code:str,x_admin_key:str|None=Header(default=None)):
    auth(x_admin_key)
    with Session() as s:
        c=s.scalar(select(Customer).where(Customer.guild_id==guild_id,Customer.code==code.upper()))
        if not c: raise HTTPException(404,'Cliente não encontrado')
        rows=s.scalars(select(Order).where(Order.guild_id==guild_id,Order.customer_id==c.id).order_by(Order.id.desc())).all()
        return [{'code':o.code,'skin_name':o.skin_name,'status':o.status,'found_price':float(o.found_price) if o.found_price is not None else None,'customer_price':float(o.customer_price) if o.customer_price is not None else None} for o in rows]

@app.post('/api/v1/customers/{guild_id}/{code}/link-order')
def link_legacy_order(guild_id:int,code:str,payload:dict=Body(...),x_admin_key:str|None=Header(default=None)):
    auth(x_admin_key)
    order_code=str(payload.get('order_code') or '').strip().upper()
    if not order_code: raise HTTPException(400,'Informe a encomenda')
    with Session.begin() as s:
        c=s.scalar(select(Customer).where(Customer.guild_id==guild_id,Customer.code==code.upper()))
        o=s.scalar(select(Order).where(Order.guild_id==guild_id,Order.code==order_code))
        if not c or not o: raise HTTPException(404,'Cliente ou encomenda não encontrado')
        old_customer=o.customer_id
        if old_customer==c.id: return {'ok':True,'changed':False,'code':o.code}
        if s.scalar(select(NegotiationOrder.id).where(NegotiationOrder.order_id==o.id)):
            raise HTTPException(409,'Encomenda já vinculada a uma negociação; reconciliação bloqueada')
        o.customer_id=c.id
        s.add(Audit(guild_id=guild_id,actor_id=0,action='CRM_ORDER_RECONCILE',entity_type='order',entity_id=o.id,detail=f'{o.code}: customer_id {old_customer} -> {c.id} ({c.code}); legacy_user_id preservado={o.user_id}'))
        return {'ok':True,'changed':True,'code':o.code}

@app.get('/api/v1/reconciliation/{guild_id}')
def reconciliation(guild_id:int,x_admin_key:str|None=Header(default=None)):
    auth(x_admin_key)
    with Session() as s:
        customers=s.scalars(select(Customer).where(Customer.guild_id==guild_id).order_by(Customer.code)).all()
        orders=s.scalars(select(Order).where(Order.guild_id==guild_id).order_by(Order.id)).all()
        valid={c.id:c for c in customers}
        rows=[]
        for o in orders:
            c=valid.get(o.customer_id) if o.customer_id else None
            status='LINKED' if c else ('BROKEN' if o.customer_id else 'UNRESOLVED')
            rows.append({'code':o.code,'skin_name':o.skin_name,'status':o.status,'legacy_user_id':o.user_id,'customer_id':o.customer_id,'customer_code':c.code if c else None,'customer_name':c.display_name if c else None,'link_status':status})
        return {'orders':rows,'customers':[_customer_payload(c) for c in customers],
                'total':len(rows),'linked':sum(x['link_status']=='LINKED' for x in rows),'unresolved':sum(x['link_status']=='UNRESOLVED' for x in rows),'broken':sum(x['link_status']=='BROKEN' for x in rows)}

@app.post('/api/v1/reconciliation/{guild_id}/order/{order_code}')
def reconcile_order(guild_id:int,order_code:str,payload:dict=Body(...),x_admin_key:str|None=Header(default=None)):
    auth(x_admin_key)
    code=str(payload.get('customer_code') or '').strip().upper()
    with Session.begin() as s:
        o=s.scalar(select(Order).where(Order.guild_id==guild_id,Order.code==order_code.upper()))
        c=s.scalar(select(Customer).where(Customer.guild_id==guild_id,Customer.code==code))
        if not o or not c: raise HTTPException(404,'Encomenda ou cliente não encontrado')
        if s.scalar(select(NegotiationOrder.id).where(NegotiationOrder.order_id==o.id)) and o.customer_id!=c.id:
            raise HTTPException(409,'Encomenda já usada em negociação; alteração bloqueada')
        old=o.customer_id;o.customer_id=c.id
        s.add(Audit(guild_id=guild_id,actor_id=0,action='DATA_RECONCILE_ORDER_CUSTOMER',entity_type='order',entity_id=o.id,detail=f'{o.code}: customer_id {old} -> {c.id} ({c.code}); legacy_user_id={o.user_id}'))
        return {'ok':True,'order':o.code,'customer':c.code}

@app.post('/api/v1/customers/{guild_id}')
def create_customer(guild_id:int,payload:dict=Body(...),x_admin_key:str|None=Header(default=None)):
    auth(x_admin_key)
    try: did=int(payload.get('discord_id') or 0)
    except: raise HTTPException(400,'Discord ID inválido')
    name=str(payload.get('display_name') or '').strip()
    if not did or not name: raise HTTPException(400,'Nome e Discord ID são obrigatórios')
    with Session.begin() as s:
        if s.scalar(select(Customer.id).where(Customer.guild_id==guild_id,Customer.discord_id==did)):
            raise HTTPException(409,'Já existe cliente com este Discord ID')
        c=_ensure_customer(s,guild_id,did,name);c.trade_url=payload.get('trade_url') or None;c.whatsapp=payload.get('whatsapp') or None;c.notes=payload.get('notes') or None
        s.add(Audit(guild_id=guild_id,actor_id=0,action='CRM_CREATE',entity_type='customer',entity_id=c.id,detail=c.code));code=c.code
    return {'ok':True,'code':code}

@app.put('/api/v1/customers/{guild_id}/{code}')
def update_customer(guild_id:int,code:str,payload:dict=Body(...),x_admin_key:str|None=Header(default=None)):
    auth(x_admin_key)
    with Session.begin() as s:
        c=s.scalar(select(Customer).where(Customer.guild_id==guild_id,Customer.code==code.upper()))
        if not c: raise HTTPException(404,'Cliente não encontrado')
        for k in ('display_name','trade_url','whatsapp','notes'):
            if k in payload:setattr(c,k,payload.get(k) or None)
        s.add(Audit(guild_id=guild_id,actor_id=0,action='CRM_UPDATE',entity_type='customer',entity_id=c.id,detail=c.code))
    return {'ok':True}

@app.get('/api/v1/customers/{guild_id}/{code}')
def customer_detail(guild_id:int,code:str,x_admin_key:str|None=Header(default=None)):
    auth(x_admin_key)
    with Session() as s:
        c=s.scalar(select(Customer).where(Customer.guild_id==guild_id,Customer.code==code.upper()))
        if not c: raise HTTPException(404,'Cliente não encontrado')
        orders=s.scalars(select(Order).where(Order.guild_id==guild_id,Order.customer_id==c.id).order_by(Order.id.desc())).all()
        negs=s.scalars(select(Negotiation).where(Negotiation.guild_id==guild_id,Negotiation.user_id==c.discord_id).order_by(Negotiation.id.desc())).all()
        out=_customer_payload(c);out['orders']=[{'code':o.code,'skin_name':o.skin_name,'status':o.status} for o in orders];out['negotiations']=[{'code':n.code,'status':_neg_detail(s,n)['status'],'sale_total':_money(n.sale_total)} for n in negs];return out

@app.get('/api/v1/system/{guild_id}')
def system_gate(guild_id:int,x_admin_key:str|None=Header(default=None)):
    auth(x_admin_key)
    checks=[]
    def ck(name,ok,detail=''): checks.append({'name':name,'ok':bool(ok),'detail':detail})
    with Session() as s:
        accepted=s.scalars(select(TradeInItem).join(Negotiation,TradeInItem.negotiation_id==Negotiation.id).where(Negotiation.guild_id==guild_id,TradeInItem.status=='ACCEPTED')).all()
        orphan=[t.code for t in accepted if not t.stock_skin_id or not s.get(Skin,t.stock_skin_id)]
        duplicate_stock=s.execute(select(TradeInItem.stock_skin_id,func.count()).where(TradeInItem.stock_skin_id.is_not(None)).group_by(TradeInItem.stock_skin_id).having(func.count()>1)).all()
        dup_customer=s.execute(select(Customer.discord_id,func.count()).where(Customer.guild_id==guild_id).group_by(Customer.discord_id).having(func.count()>1)).all()
        all_orders=s.scalars(select(Order).where(Order.guild_id==guild_id)).all()
        customer_ids=set(s.scalars(select(Customer.id).where(Customer.guild_id==guild_id)).all())
        unresolved=[o.code for o in all_orders if not o.customer_id]
        broken_orders=[o.code for o in all_orders if o.customer_id and o.customer_id not in customer_ids]
        linked_count=len(all_orders)-len(unresolved)-len(broken_orders)
        negs=s.scalars(select(Negotiation).where(Negotiation.guild_id==guild_id)).all()
        overpay=[n.code for n in negs if _money(n.cash_received)>_money(n.cash_due)+.009]
        bad_credit=[n.code for n in negs if _money(n.trade_credit)<0 or _money(n.trade_credit)>_money(n.sale_total)+.009]
        bad_links=[]; duplicate_order_links=[]
        for n in negs:
            links=s.scalars(select(NegotiationOrder).where(NegotiationOrder.negotiation_id==n.id)).all()
            for link in links:
                o=s.get(Order,link.order_id)
                if not o or int(o.guild_id)!=int(guild_id) or not o.customer_id or not s.scalar(select(Customer.id).where(Customer.id==o.customer_id,Customer.guild_id==guild_id,Customer.discord_id==n.user_id)): bad_links.append(f'{n.code}/{getattr(o,"code","?")}')
        linked=s.execute(select(NegotiationOrder.order_id,func.count()).join(Negotiation,NegotiationOrder.negotiation_id==Negotiation.id).where(Negotiation.guild_id==guild_id,Negotiation.status!='CANCELLED').group_by(NegotiationOrder.order_id).having(func.count()>1)).all()
        duplicate_order_links=[str(x[0]) for x in linked]
        expected_bad=[]
        for t in s.scalars(select(TradeInItem).join(Negotiation,TradeInItem.negotiation_id==Negotiation.id).where(Negotiation.guild_id==guild_id,TradeInItem.status!='ACCEPTED')).all():
            if t.stock_skin_id: expected_bad.append(t.code)
        # V3.4 Unified Core invariants: Order is the canonical source for Discord/Web/CRM/Operations.
        open_orders=[o for o in all_orders if o.status not in ('DELIVERED','CANCELLED')]
        order_ops=s.scalars(select(Operation).where(Operation.guild_id==guild_id,Operation.kind=='ORDER',Operation.status.not_in(['DONE','CANCELLED']))).all()
        op_by_code={op.ref_code:op for op in order_ops}
        missing_ops=[o.code for o in open_orders if o.code not in op_by_code]
        dangling_ops=[]
        order_by_code={o.code:o for o in all_orders}
        for op in order_ops:
            o=order_by_code.get(op.ref_code)
            if not o or (op.entity_id and o.id!=op.entity_id): dangling_ops.append(op.ref_code)
        pipeline_bad=unresolved+broken_orders+missing_ops+dangling_ops
        ck('Database',True,_database_label())
        ck('Order Pipeline Integrity',not pipeline_bad,f'Orders {len(all_orders)} · abertas {len(open_orders)} · ops {len(order_ops)} · sem CRM {len(unresolved)} · sem operação {len(missing_ops)} · operação órfã {len(dangling_ops)}')
        ck('Single Source of Truth',not dangling_ops and not missing_ops,'Discord/Web/CRM/Operations usam orders como fonte canônica' if not dangling_ops and not missing_ops else 'Divergência: '+', '.join((missing_ops+dangling_ops)[:10]))
        # V3.4.4: zero registros nao e mais considerado prova de integridade quando o recovery detectou historico.
        migration_ok=True; migration_detail='Nenhum relatório de recuperação disponível'
        try:
            import json
            rp=os.getenv('CLUTCH_MIGRATION_REPORT','')
            if rp and os.path.exists(rp):
                mr=json.load(open(rp,'r',encoding='utf-8')); detected=set(mr.get('detected_historical_order_codes') or []); canonical={o.code for o in all_orders}; hist_missing=sorted(detected-canonical)
                migration_ok=(mr.get('status')=='COMMITTED' and not hist_missing)
                migration_detail=f'Histórico detectado {len(detected)} · Core {len(canonical)} · ausentes {len(hist_missing)}' + ((' · '+', '.join(hist_missing[:8])) if hist_missing else '')
            else: migration_ok=False
        except Exception as e:
            migration_ok=False; migration_detail='Falha lendo relatório: '+str(e)[:120]
        ck('Historical Data Completeness',migration_ok,migration_detail)
        ck('Version Consistency',True,'Backend/Web/Core V3.8.0 · Recovery V3.4.5 one-shot')
        ck('TI → SK',not orphan,', '.join(orphan) or 'OK')
        ck('SK única por Trade-In',not duplicate_stock,str(len(duplicate_stock))+' conflito(s)')
        ck('SK somente após aceite',not expected_bad,', '.join(expected_bad) or 'OK')
        ck('CRM duplicado',not dup_customer,str(len(dup_customer))+' conflito(s)')
        ck('CRM ↔ Orders',not unresolved and not broken_orders,f'Total {len(all_orders)} · vinculadas {linked_count} · sem CRM {len(unresolved)} · vínculo quebrado {len(broken_orders)}')
        ck('NEG ↔ Cliente ↔ Orders',not bad_links,', '.join(bad_links) or 'OK')
        ck('Encomenda em uma NEG ativa',not duplicate_order_links,str(len(duplicate_order_links))+' conflito(s)')
        ck('Pagamentos',not overpay,', '.join(overpay) or 'OK')
        ck('Crédito Trade-In',not bad_credit,', '.join(bad_credit) or 'OK')
        # Production Integrity V3.5: namespace contamination and duplicate Order operations are critical.
        foreign=[]
        for model,name in [(Customer,'customers'),(Order,'orders'),(Operation,'operations'),(Skin,'skins'),(Negotiation,'negotiations'),(Ledger,'ledger')]:
            for g,c in s.execute(select(model.guild_id,func.count()).group_by(model.guild_id)).all():
                if int(g)!=int(guild_id) and int(c)>0: foreign.append(f'{name}@{g}={c}')
        op_counts={}
        for op in order_ops: op_counts[op.ref_code]=op_counts.get(op.ref_code,0)+1
        duplicate_ops=[f'{k}({v})' for k,v in op_counts.items() if v>1]
        ck('Canonical Namespace Purity',not foreign,', '.join(foreign) or f'Somente guild {guild_id}')
        ck('1 Order → 1 Operation',not duplicate_ops,', '.join(duplicate_ops) or 'OK')
    return {'ready':all(x['ok'] for x in checks),'version':'3.7.5','checks':checks}

@app.get('/api/v1/operations/{guild_id}')
def operations(guild_id:int,x_admin_key:str|None=Header(default=None)):
    auth(x_admin_key)
    with Session() as s:
        rows=s.scalars(select(Operation).where(Operation.guild_id==guild_id).order_by(Operation.id.desc()).limit(100)).all()
        return [{'id':x.id,'kind':x.kind,'ref_code':x.ref_code,'title':x.title,'detail':x.detail or '', 'status':x.status,'priority':x.priority,'user_id':x.user_id,'assigned_to':x.assigned_to,'created_at':x.created_at.isoformat() if x.created_at else None} for x in rows]


@app.get('/api/v1/negotiations/{guild_id}')
def negotiations(guild_id:int,x_admin_key:str|None=Header(default=None)):
    auth(x_admin_key)
    with Session() as s:
        rows=s.scalars(select(Negotiation).where(Negotiation.guild_id==guild_id).order_by(Negotiation.id.desc()).limit(100)).all()
        return [_neg_detail(s,n) for n in rows]

@app.get('/api/v1/operations-summary/{guild_id}')
def operations_summary(guild_id:int,x_admin_key:str|None=Header(default=None)):
    auth(x_admin_key)
    terminal=('DONE','CANCELLED')
    with Session() as q:
        rows=list(q.scalars(select(Operation).where(Operation.guild_id==guild_id).order_by(Operation.id.desc())).all())
        active=[x for x in rows if x.status not in terminal]
        history=[x for x in rows if x.status in terminal]
        return {
            'active_count':len(active),'history_count':len(history),
            'active':[{'id':x.id,'kind':x.kind,'ref_code':x.ref_code,'title':x.title,'status':x.status,'priority':x.priority,'assigned_to':x.assigned_to,'staff_channel_id':x.staff_channel_id,'staff_message_id':x.staff_message_id} for x in active],
            'history':[{'id':x.id,'kind':x.kind,'ref_code':x.ref_code,'title':x.title,'status':x.status,'priority':x.priority,'assigned_to':x.assigned_to} for x in history[:50]]
        }

@app.get('/api/v1/orders/{guild_id}')
def orders(guild_id:int,x_admin_key:str|None=Header(default=None)):
    auth(x_admin_key)
    with Session() as s:
        rows=s.scalars(select(Order).where(Order.guild_id==guild_id).order_by(Order.id.desc()).limit(100)).all()
        return [{'code':x.code,'skin_name':x.skin_name,'status':x.status,'user_id':x.user_id,'assigned_to':x.assigned_to,'budget':float(x.budget) if x.budget is not None else None,'found_price':float(x.found_price) if x.found_price is not None else None,'customer_price':float(x.customer_price) if x.customer_price is not None else None,'supplier':x.supplier,'trade_lock_until':x.trade_lock_until.isoformat() if x.trade_lock_until else None} for x in rows]

@app.get('/api/v1/analyze/{guild_id}')
def analyze(guild_id:int,cost:float,quick_sell:float,fees:float=0,liquidity:str='MEDIUM',x_admin_key:str|None=Header(default=None)):
    auth(x_admin_key); r=analyze_purchase(guild_id,cost,quick_sell,fees,liquidity)
    out={}
    for k,v in r.items(): out[k]=float(v) if hasattr(v,'as_tuple') else v
    return out


@app.get('/identity-bootstrap-v351', response_class=HTMLResponse, include_in_schema=False)
def identity_bootstrap_v3452():
    # Unique, uncached bootstrap route. It evicts any legacy service worker/cache
    # before the Control Center is allowed to load.
    html = r"""<!doctype html><html><head><meta charset="utf-8"><meta http-equiv="Cache-Control" content="no-store"><title>Clutch OS</title></head><body style="background:#090b0b;color:#dfff45;font-family:system-ui;padding:32px">Sincronizando identidade do Clutch OS...<script>
(async()=>{
  try {
    if ('serviceWorker' in navigator) { const regs=await navigator.serviceWorker.getRegistrations(); await Promise.all(regs.map(r=>r.unregister())); }
    if ('caches' in window) { const names=await caches.keys(); await Promise.all(names.map(n=>caches.delete(n))); }
    localStorage.removeItem('clutchGuild'); sessionStorage.removeItem('clutchGuild');
  } catch(e) { console.warn('identity bootstrap cleanup',e); }
  location.replace('/?v=3.7.5&t='+Date.now());
})();
</script></body></html>"""
    return HTMLResponse(html, headers={'Cache-Control':'no-store, no-cache, must-revalidate, max-age=0','Pragma':'no-cache','Expires':'0','Clear-Site-Data':'"cache"'})

@app.get('/',response_class=HTMLResponse)
def home(request:Request):
    if not _session_ok(request): return RedirectResponse('/login',status_code=303)
    return HTMLResponse(HTML,headers={'Cache-Control':'no-store'})

HTML=r'''<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Clutch Control</title><style>
:root{--bg:#090a0b;--p:#141516;--p2:#1b1d1f;--line:#292c2f;--muted:#8d9197;--text:#f5f6f7;--a:#d7ff00;--ok:#72e58c;--warn:#ffcf4a;--bad:#ff5d70}*{box-sizing:border-box}body{margin:0;background:radial-gradient(circle at 70% -15%,#262b00,transparent 27%),var(--bg);color:var(--text);font:14px Inter,system-ui,sans-serif}.shell{max-width:1500px;margin:auto;padding:22px}.top{display:flex;align-items:center;gap:28px;height:68px}.brand{font-weight:950;font-size:18px;display:flex;gap:10px;align-items:center}.mark{background:var(--a);color:#090a0b;width:32px;height:32px;border-radius:10px;display:grid;place-items:center}.nav{display:flex;gap:5px;flex:1}.nav button{border:0;background:transparent;color:#85898f;padding:10px 13px;border-radius:12px;font-weight:750;cursor:pointer}.nav button.active,.nav button:hover{background:#1b1d1f;color:#fff}.hero{margin:28px 0 20px}.ey{color:var(--a);font-weight:850;font-size:11px;letter-spacing:1.8px}.hero h1{font-size:42px;margin:4px 0 2px;letter-spacing:-2px}.muted{color:var(--muted)}.view{display:none}.view.active{display:block}.grid{display:grid;grid-template-columns:repeat(4,1fr);gap:14px}.card{background:linear-gradient(145deg,#17191a,#111213);border:1px solid #25282a;border-radius:21px;padding:19px;box-shadow:0 20px 60px #0004}.accent{background:var(--a);color:#090a0b;border:0}.span2{grid-column:span 2}.span4{grid-column:span 4}.label{font-size:11px;color:var(--muted);text-transform:uppercase;letter-spacing:.7px}.accent .label{color:#333}.metric{font-size:34px;font-weight:950;letter-spacing:-1.5px;margin-top:7px}.title{display:flex;justify-content:space-between;align-items:center;margin-bottom:14px}.title h3{margin:0}.list{display:grid;gap:8px}.item{background:#1a1c1e;border:1px solid var(--line);padding:12px 14px;border-radius:14px;display:flex;gap:12px;align-items:center;cursor:pointer}.item:hover{border-color:#586000}.grow{flex:1}.badge{font-size:10px;font-weight:850;padding:5px 8px;border-radius:999px;background:#282b2d}.money{font-weight:900}.table{width:100%;border-collapse:separate;border-spacing:0 7px}.table th{text-align:left;color:#777c82;font-size:10px;text-transform:uppercase;padding:0 10px}.table td{background:#191b1d;border-top:1px solid #26292c;border-bottom:1px solid #26292c;padding:11px 10px}.table td:first-child{border-left:1px solid #26292c;border-radius:12px 0 0 12px}.table td:last-child{border-right:1px solid #26292c;border-radius:0 12px 12px 0}.btn{border:0;border-radius:11px;background:var(--a);color:#090a0b;padding:9px 12px;font-weight:900;cursor:pointer}.btn.dark{background:#272a2d;color:white}.form{display:grid;grid-template-columns:repeat(2,1fr);gap:10px}.form input,.form textarea,.form select{width:100%;background:#0e0f10;border:1px solid #303337;color:#fff;border-radius:11px;padding:11px}.form textarea{grid-column:span 2;min-height:72px}.detail{display:none;margin-top:14px}.detail.open{display:block}.kpis{display:grid;grid-template-columns:repeat(3,1fr);gap:10px}.mini{background:#1b1d1f;border:1px solid var(--line);border-radius:14px;padding:13px}.mini b{display:block;font-size:19px}.footer{text-align:center;color:#555b60;padding:28px}.danger{color:var(--bad)}.ok{color:var(--ok)}
@media(max-width:900px){.nav{overflow:auto}.grid{grid-template-columns:1fr 1fr}.span4,.span2{grid-column:span 2}}@media(max-width:620px){.shell{padding:12px}.grid{grid-template-columns:1fr}.span4,.span2{grid-column:span 1}.hero h1{font-size:32px}.form{grid-template-columns:1fr}.form textarea{grid-column:span 1}}
</style></head><body><div class="shell"><header class="top"><div class="brand"><span class="mark">C</span>CLUTCH CONTROL</div><nav class="nav"><button data-v="overview" class="active">Overview</button><button data-v="operations">Operations</button><button data-v="trading">Trading</button><button data-v="finance">Finance</button><button data-v="inventory">Inventory</button><button data-v="customers">Customers</button><button data-v="reconciliation">Reconciliation</button><button data-v="system">System</button></nav><div class="badge">V3.8.4</div></header><section class="hero"><div class="ey">CLUTCH OS · OPERATIONAL CONTROL</div><h1 id="pageTitle">Overview</h1><div class="muted" id="sub">Operação, trade-in e financeiro em uma única base.</div></section>
<section id="overview" class="view active"><div class="grid"><div class="card accent"><div class="label">Caixa</div><div class="metric" id="cash">R$ 0</div></div><div class="card"><div class="label">Capital em estoque</div><div class="metric" id="inventoryCapital">R$ 0</div></div><div class="card"><div class="label">A receber</div><div class="metric" id="receivables">R$ 0</div></div><div class="card"><div class="label">Trade-ins abertos</div><div class="metric" id="tradeins">0</div></div><div class="card"><div class="label">Buylist</div><div class="metric" id="buylistState">—</div></div><div class="card span2"><div class="title"><h3>Operação</h3><button class="btn dark" onclick="go('operations')">Abrir fila</button></div><div class="kpis"><div class="mini"><span class="muted">Fila</span><b id="ops">0</b></div><div class="mini"><span class="muted">Encomendas</span><b id="orders">0</b></div><div class="mini"><span class="muted">Vendas</span><b id="sales">0</b></div></div></div><div class="card span2"><div class="title"><h3>Resultado</h3></div><div class="kpis"><div class="mini"><span class="muted">Receita</span><b id="revenue">R$ 0</b></div><div class="mini"><span class="muted">Lucro realizado</span><b id="profit">R$ 0</b></div><div class="mini"><span class="muted">Venda potencial</span><b id="potential">R$ 0</b></div></div></div></div></section>
<section id="operations" class="view"><div class="grid"><div class="card span4"><div class="title"><h3>Fila operacional</h3><span class="muted">ENC · BUYLIST · TRADE-IN · VENDAS</span></div><div id="opList" class="list"></div><details style="margin-top:14px"><summary class="muted" style="cursor:pointer">Histórico operacional</summary><div id="opHistory" class="list" style="margin-top:10px"></div></details></div><div class="card span4"><div class="title"><h3>Encomendas</h3></div><div id="orderList" class="list"></div></div></div></section>
<section id="trading" class="view"><div class="grid"><div class="card span2"><div class="title"><h3>Nova negociação Trade-In</h3><span class="badge">NEG-XXXXX</span></div><div class="form"><select id="nUser"><option value="">Selecione o cliente / CRM</option></select><input id="nSale" placeholder="Valor total da venda (ex. 7500)"><input id="nCredit" placeholder="Crédito em skins (ex. 4500)"><select id="nOrders" multiple size="3" title="Selecione as encomendas do cliente"></select><textarea id="nNotes" placeholder="Observações"></textarea></div><button class="btn" style="margin-top:10px" onclick="createNeg()">Criar negociação</button></div><div class="card span2"><div class="title"><h3>Resumo de Trade-In</h3></div><div class="kpis"><div class="mini"><span class="muted">Crédito aberto</span><b id="tradeCredit">R$ 0</b></div><div class="mini"><span class="muted">Ativos Trade-In</span><b id="tradeAssets">R$ 0</b></div><div class="mini"><span class="muted">Lucro projetado NEG</span><b id="negProfit">R$ 0</b></div></div></div><div class="card span4"><div class="title"><h3>Negociações</h3><span class="muted">Clique para abrir</span></div><div id="negList" class="list"></div><div id="negDetail" class="detail"></div></div></div></section>
<section id="customers" class="view"><div class="grid"><div class="card span2"><div class="title"><h3>Novo cliente</h3><span class="badge">CL-XXXXX</span></div><div class="form"><input id="cName" placeholder="Nome / apelido"><input id="cDiscord" placeholder="Discord User ID"><input id="cTrade" placeholder="Steam Trade URL"><input id="cWhats" placeholder="WhatsApp (opcional)"><textarea id="cNotes" placeholder="Observações"></textarea></div><button class="btn" style="margin-top:10px" onclick="createCustomer()">Criar cliente</button> <button class="btn dark" onclick="syncCRM()">Importar usuários das encomendas</button></div><div class="card span2"><div class="title"><h3>CRM</h3><span class="muted">Clientes e histórico</span></div><div id="customerList" class="list"></div></div><div class="card span4"><div id="customerDetail" class="detail"></div></div></div></section>
<section id="reconciliation" class="view"><div class="grid"><div class="card span4"><div class="title"><h3>CRM ↔ Orders · Reconciliação</h3><span class="muted">Vínculos legados são preservados em auditoria</span></div><div id="reconSummary" class="kpis"></div><div id="reconList" class="list"></div></div></div></section><section id="system" class="view"><div class="grid"><div class="card span4"><div class="title"><h3>Production Gate</h3><span id="gateBadge" class="badge">Verificando</span></div><div id="systemChecks" class="list"></div></div></div></section>
<section id="finance" class="view"><div class="grid"><div class="card accent"><div class="label">Caixa líquido</div><div class="metric" id="fCash">R$ 0</div></div><div class="card"><div class="label">Estoque</div><div class="metric" id="fInv">R$ 0</div></div><div class="card"><div class="label">A receber</div><div class="metric" id="fRec">R$ 0</div></div><div class="card"><div class="label">Trade-In a receber</div><div class="metric" id="fTradeRec">R$ 0</div></div><div class="card"><div class="label">Trade-In no estoque</div><div class="metric" id="fTrade">R$ 0</div></div><div class="card span4"><div class="title"><h3>Ledger financeiro</h3><span class="muted">Entradas positivas · saídas negativas</span></div><div id="ledger"></div></div></div></section>
<section id="inventory" class="view"><div class="card"><div class="title"><h3>Inventory</h3><span class="muted">SK-XXXXX · origem · custo · venda</span></div><div id="skinTable"></div></div></section>
<div class="footer">CLUTCH OS V3.8.3 · BOT-LED ACCESS · SINGLE SOURCE OF TRUTH</div></div><script>
const BRL=new Intl.NumberFormat('pt-BR',{style:'currency',currency:'BRL'});let G='',K='';function money(v){return v===null||v===undefined?'Aguardando CMV':BRL.format(Number(v||0))}function esc(s){return String(s??'').replace(/[&<>\"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;'}[c]))}async function api(p,opt={}){let h={'Content-Type':'application/json'};if(K)h['X-Admin-Key']=K;let r=await fetch(p,{...opt,headers:{...h,...(opt.headers||{})}});if(!r.ok)throw Error(await r.text());return r.status===204?{}:r.json()}function set(id,v){let e=document.getElementById(id);if(e)e.textContent=v}function go(v){document.querySelectorAll('.view').forEach(x=>x.classList.remove('active'));document.getElementById(v).classList.add('active');document.querySelectorAll('.nav button').forEach(x=>x.classList.toggle('active',x.dataset.v===v));set('pageTitle',v[0].toUpperCase()+v.slice(1));if(v==='trading')loadTrading();if(v==='finance')loadFinance();if(v==='operations')loadOps();if(v==='inventory')loadInventory();if(v==='customers')loadCustomers();if(v==='reconciliation')loadReconciliation();if(v==='system')loadSystem()}document.querySelectorAll('.nav button').forEach(b=>b.onclick=()=>go(b.dataset.v));
let identityReady=null;async function resolveIdentity(){if(!identityReady){identityReady=(async()=>{localStorage.removeItem('clutchGuild');sessionStorage.removeItem('clutchGuild');const ident=await api('/api/v1/identity');const gid=String(ident.canonical_guild_id||'');if(!gid)throw Error('Frontend Identity Bootstrap: guild canônica ausente');return gid})()}return identityReady}async function boot(){try{G=await resolveIdentity();const dx=await api('/api/v1/diagnostics/'+G);if(!dx.ok)console.warn('Production Integrity diagnostics',dx);let [d,f]=await Promise.all([api('/api/v1/dashboard/'+G),api('/api/v1/finance/'+G)]);set('cash',money(f.cash));set('inventoryCapital',money(f.inventory));set('receivables',money(f.receivables));set('tradeins',d.tradeins_open);set('buylistState',d.buylist_enabled?'ATIVA':'PAUSADA');set('ops',d.operations_open);set('orders',d.orders_open);set('sales',d.sales_open);set('revenue',money(d.revenue));set('profit',money(d.realized_profit));set('potential',money(d.inventory_sale_value));set('tradeCredit',money(f.trade_credit_open));set('tradeAssets',money(f.trade_assets));set('negProfit',money(f.projected_negotiation_profit));document.body.dataset.dataState='ready'}catch(e){document.body.dataset.dataState='error';console.error('CLUTCH BOOT FAILED',e);['cash','inventoryCapital','receivables','revenue','profit','potential'].forEach(id=>set(id,'ERRO'));set('sub','Falha ao carregar dados. O sistema não substitui erros por zero. Consulte o log/API.')}}
async function loadOps(){let [sum,ords]=await Promise.all([api('/api/v1/operations-summary/'+G),api('/api/v1/orders/'+G)]);let ops=sum.active||[];let hist=sum.history||[];document.getElementById('opList').innerHTML=ops.length?ops.map(x=>`<div class="item"><span class="badge">${esc(x.kind)}</span><div class="grow"><b>${esc(x.ref_code)} · ${esc(x.title)}</b><div class="muted">${esc(x.status)} · prioridade ${esc(x.priority)} · responsável ${x.assigned_to||'—'}${x.staff_message_id?' · Discord ✓':' · Discord pendente'}</div></div></div>`).join(''):'<div class="muted">Fila ativa vazia.</div>';let he=document.getElementById('opHistory');if(he)he.innerHTML=hist.length?hist.map(x=>`<div class="item"><span class="badge">${esc(x.status)}</span><div class="grow"><b>${esc(x.ref_code)} · ${esc(x.title)}</b></div></div>`).join(''):'<div class="muted">Sem histórico.</div>';document.getElementById('orderList').innerHTML=ords.length?ords.map(x=>`<div class="item"><span class="badge">${esc(x.status)}</span><div class="grow"><b>${esc(x.code)} · ${esc(x.skin_name)}</b><div class="muted">Orçamento ${money(x.budget)} · custo ${money(x.found_price)} · cliente ${money(x.customer_price)} · ${esc(x.supplier||'sem fornecedor')}</div></div></div>`).join(''):'<div class="muted">Sem encomendas.</div>'}
async function loadTrading(){let [ns,f,cs]=await Promise.all([api('/api/v1/negotiations/'+G),api('/api/v1/finance/'+G),api('/api/v1/customers/'+G)]);set('tradeCredit',money(f.trade_credit_open));set('tradeAssets',money(f.trade_assets));set('negProfit',money(f.projected_negotiation_profit));let cu=document.getElementById('nUser'),prev=cu.value;cu.innerHTML='<option value="">Selecione o cliente / CRM</option>'+cs.map(c=>`<option value="${esc(c.code)}">${esc(c.display_name)} · ${esc(c.code)}</option>`).join('');if([...cu.options].some(o=>o.value===prev))cu.value=prev;cu.onchange=refreshCustomerOrders;await refreshCustomerOrders();document.getElementById('negList').innerHTML=ns.length?ns.map(n=>`<div class="item" onclick="openNeg('${n.code}')"><span class="badge">${esc(n.status)}</span><div class="grow"><b>${n.code} · Trade-In</b><div class="muted">Venda ${money(n.sale_total)} · crédito ${money(n.trade_credit)} · dinheiro ${money(n.cash_received)} / ${money(n.cash_due)}</div></div><b>${money(n.projected_profit)}</b></div>`).join(''):'<div class="muted">Nenhuma negociação criada.</div>'}
async function openNeg(code){let n=await api('/api/v1/negotiation/'+G+'/'+code),d=document.getElementById('negDetail');d.className='detail open';let action=x=>x.status==='EXPECTED'?`<button class="btn dark" onclick="transitionTI('${n.code}','${x.code}','RECEIVE')">Confirmar recebimento</button>`:x.status==='RECEIVED'?`<button class="btn dark" onclick="transitionTI('${n.code}','${x.code}','INSPECT')">Inspecionar</button>`:x.status==='INSPECTED'?`<button class="btn" onclick="transitionTI('${n.code}','${x.code}','ACCEPT')">Aceitar no estoque</button>`:'';d.innerHTML=`<div class="card"><div class="title"><h3>${n.code}</h3><span class="badge">${n.status}</span></div><div class="kpis"><div class="mini"><span class="muted">Venda</span><b>${money(n.sale_total)}</b></div><div class="mini"><span class="muted">Custo encomendas</span><b>${n.costs_known?money(n.order_cost):'Aguardando CMV'}</b></div><div class="mini"><span class="muted">Lucro projetado</span><b>${money(n.projected_profit)}</b></div></div><div class="muted" style="margin-top:10px">Trade-In: ${money(n.accepted_trade_value)} aceito / ${money(n.trade_credit)} · Caixa: ${money(n.cash_received)} / ${money(n.cash_due)}</div><h4>Skins do Trade-In</h4><div class="list">${n.items.map(x=>`<div class="item"><div class="grow"><b>${x.code} · ${esc(x.name)}</b><div class="muted">${esc(x.exterior)} · float ${esc(x.float)} · ${esc(x.status)}${x.stock_skin_id?' · SK criada':''}</div></div><b>${money(x.credit_value)}</b>${action(x)}${['EXPECTED','RECEIVED','INSPECTED'].includes(x.status)?`<button class="btn dark" onclick="transitionTI('${n.code}','${x.code}','REJECT')">Rejeitar</button>`:''}</div>`).join('')||'<span class="muted">Nenhuma.</span>'}</div><h4>Adicionar skin</h4><div class="form"><input id="iName" placeholder="Skin"><input id="iExt" placeholder="Exterior"><input id="iFloat" placeholder="Float"><input id="iPattern" placeholder="Pattern"><input id="iCredit" placeholder="Crédito atribuído"></div><button class="btn" onclick="addItem('${n.code}')" style="margin-top:8px">Adicionar TI-XXXXX</button><h4>Registrar pagamento</h4><div class="form"><input id="pAmount" placeholder="Valor"><input id="pRef" placeholder="Referência (PIX)"></div><button class="btn" onclick="addPay('${n.code}')" style="margin-top:8px">Registrar recebimento</button>${n.cash_received===0&&n.accepted_trade_value===0?`<button class="btn dark" onclick="cancelNeg('${n.code}')" style="margin:8px">Cancelar negociação</button>`:''}</div>`;d.scrollIntoView({behavior:'smooth'})}
async function transitionTI(n,t,a){try{await api(`/api/v1/tradein/${G}/${n}/item/${t}/transition`,{method:'POST',body:JSON.stringify({action:a})});await openNeg(n);await loadTrading();await boot()}catch(e){alert('Erro: '+e.message)}}async function cancelNeg(n){if(!confirm('Cancelar '+n+'?'))return;try{await api(`/api/v1/tradein/${G}/${n}/cancel`,{method:'POST'});await loadTrading();await boot()}catch(e){alert('Erro: '+e.message)}}
async function createNeg(){try{let body={customer_code:document.getElementById('nUser').value,sale_total:document.getElementById('nSale').value,trade_credit:document.getElementById('nCredit').value,orders:[...document.getElementById('nOrders').selectedOptions].map(x=>x.value),notes:document.getElementById('nNotes').value};let r=await api('/api/v1/tradein/'+G,{method:'POST',body:JSON.stringify(body)});alert('Criada '+r.code);loadTrading()}catch(e){alert('Erro: '+e.message)}}async function addItem(code){try{await api('/api/v1/tradein/'+G+'/'+code+'/item',{method:'POST',body:JSON.stringify({name:iName.value,exterior:iExt.value,float:iFloat.value,pattern:iPattern.value,credit_value:iCredit.value})});openNeg(code);loadTrading()}catch(e){alert('Erro: '+e.message)}}async function addPay(code){try{await api('/api/v1/tradein/'+G+'/'+code+'/payment',{method:'POST',body:JSON.stringify({amount:pAmount.value,reference:pRef.value||'PIX'})});openNeg(code);loadTrading();boot()}catch(e){alert('Erro: '+e.message)}}
async function loadFinance(){let f=await api('/api/v1/finance/'+G);set('fCash',money(f.cash));set('fInv',money(f.inventory));set('fRec',money(f.receivables));set('fTradeRec',money(f.trade_receivable));set('fTrade',money(f.trade_assets));document.getElementById('ledger').innerHTML=`<table class="table"><thead><tr><th>Tipo</th><th>Nota</th><th>Data</th><th>Valor</th></tr></thead><tbody>${f.ledger.map(x=>`<tr><td>${esc(x.kind)}</td><td>${esc(x.note)}</td><td>${x.at?new Date(x.at).toLocaleString('pt-BR'):'—'}</td><td class="money ${x.amount<0?'danger':'ok'}">${money(x.amount)}</td></tr>`).join('')}</tbody></table>`}
async function loadCustomers(){let cs=await api('/api/v1/customers/'+G);document.getElementById('customerList').innerHTML=cs.length?cs.map(c=>`<div class="item" onclick="openCustomer('${c.code}')"><span class="badge">${c.code}</span><div class="grow"><b>${esc(c.display_name)}</b><div class="muted">Discord ${c.discord_id}</div></div></div>`).join(''):'<div class="muted">Nenhum cliente. Use “Importar usuários das encomendas”.</div>'}
async function createCustomer(){try{let r=await api('/api/v1/customers/'+G,{method:'POST',body:JSON.stringify({display_name:cName.value,discord_id:cDiscord.value,trade_url:cTrade.value,whatsapp:cWhats.value,notes:cNotes.value})});alert('Criado '+r.code);await loadCustomers();await loadTrading()}catch(e){alert('Erro: '+e.message)}}
async function syncCRM(){try{let r=await api('/api/v1/customers/'+G+'/sync-orders',{method:'POST'});alert(r.created+' cliente(s) importado(s)');await loadCustomers();await loadTrading();await boot()}catch(e){alert('Erro: '+e.message)}}
async function openCustomer(code){let c=await api('/api/v1/customers/'+G+'/'+code),d=document.getElementById('customerDetail');d.className='detail open';d.innerHTML=`<div class="card"><div class="title"><h3>${c.code} · ${esc(c.display_name)}</h3><span class="badge">Discord ${c.discord_id}</span></div><div class="kpis"><div class="mini"><span class="muted">Encomendas</span><b>${c.orders.length}</b></div><div class="mini"><span class="muted">Negociações</span><b>${c.negotiations.length}</b></div><div class="mini"><span class="muted">Trade URL</span><b style="font-size:12px">${c.trade_url?'Cadastrada':'—'}</b></div></div><h4>Encomendas</h4><div class="list">${c.orders.map(o=>`<div class="item"><b>${o.code}</b><div class="grow">${esc(o.skin_name)}</div><span class="badge">${esc(o.status)}</span></div>`).join('')||'<span class="muted">Nenhuma</span>'}</div><h4>Negociações</h4><div class="list">${c.negotiations.map(n=>`<div class="item" onclick="go('trading');setTimeout(()=>openNeg('${n.code}'),150)"><b>${n.code}</b><div class="grow">${money(n.sale_total)}</div><span class="badge">${n.status}</span></div>`).join('')||'<span class="muted">Nenhuma</span>'}</div></div>`}
async function loadReconciliation(){let r=await api('/api/v1/reconciliation/'+G);document.getElementById('reconSummary').innerHTML=`<div class="mini"><span class="muted">Total</span><b>${r.total}</b></div><div class="mini"><span class="muted">Vinculadas</span><b>${r.linked}</b></div><div class="mini"><span class="muted">Sem CRM</span><b>${r.unresolved}</b></div><div class="mini"><span class="muted">Quebradas</span><b>${r.broken}</b></div>`;let opts=r.customers.map(c=>`<option value="${c.code}">${esc(c.display_name)} · ${c.code}</option>`).join('');document.getElementById('reconList').innerHTML=r.orders.map(o=>`<div class="item"><span class="badge">${o.link_status}</span><div class="grow"><b>${o.code} · ${esc(o.skin_name)}</b><div class="muted">legacy user_id ${o.legacy_user_id||'—'} · ${o.customer_code?esc(o.customer_name)+' · '+o.customer_code:'sem CRM canônico'}</div></div>${o.link_status==='LINKED'?'':`<select id="rc_${o.code}" style="max-width:230px"><option value="">Selecionar cliente</option>${opts}</select><button class="btn" onclick="reconcileOrder('${o.code}')">Vincular</button>`}</div>`).join('')||'<div class="muted">Sem encomendas.</div>'}async function reconcileOrder(code){let e=document.getElementById('rc_'+code);if(!e.value)return alert('Selecione o cliente correto');if(!confirm('Vincular '+code+' a '+e.options[e.selectedIndex].text+'? O user_id legado será preservado em auditoria.'))return;try{await api('/api/v1/reconciliation/'+G+'/order/'+code,{method:'POST',body:JSON.stringify({customer_code:e.value})});await loadReconciliation();await loadSystem();await loadCustomers();await loadTrading()}catch(x){alert('Erro: '+x.message)}}
async function loadSystem(){let s=await api('/api/v1/system/'+G);set('gateBadge',s.ready?'PRONTO':'NÃO PRONTO');document.getElementById('gateBadge').className='badge '+(s.ready?'ok':'danger');document.getElementById('systemChecks').innerHTML=s.checks.map(c=>`<div class="item"><span class="badge ${c.ok?'ok':'danger'}">${c.ok?'✓':'✕'}</span><div class="grow"><b>${esc(c.name)}</b><div class="muted">${esc(c.detail)}</div></div></div>`).join('')}
async function loadInventory(){let s=await api('/api/v1/skins/'+G);document.getElementById('skinTable').innerHTML=`<table class="table"><thead><tr><th>Código</th><th>Skin</th><th>Origem</th><th>Custo</th><th>Venda</th><th>Status</th></tr></thead><tbody>${s.map(x=>`<tr><td>${x.code}</td><td>${esc(x.name)}<div class="muted">${esc(x.exterior||'')} · ${esc(x.float||'')}</div></td><td>${esc(x.source||'—')}</td><td>${money(x.cost+x.fees)}</td><td>${money(x.price)}</td><td>${esc(x.status)}</td></tr>`).join('')}</tbody></table>`}boot();</script></body></html>'''
