import discord
from discord import app_commands
from discord.ext import commands,tasks
from sqlalchemy import select
from datetime import datetime,timezone,timedelta
from zoneinfo import ZoneInfo
import os
import asyncio

def utc_aware(dt):
    """Normalize SQLite/SQLAlchemy datetimes to timezone-aware UTC."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)

CLUTCH_TZ = ZoneInfo("America/Sao_Paulo")

def parse_trade_lock(value):
    """Parse staff-entered Trade Lock as Sao Paulo local time and persist as UTC.
    Date-only input means end of that local day, avoiding an already-expired midnight lock.
    """
    raw=(value or '').strip()
    if not raw:
        raise ValueError('Informe o Trade Lock em DD/MM/AAAA HH:MM (ou somente DD/MM/AAAA).')
    for fmt in ('%d/%m/%Y %H:%M','%d/%m/%Y'):
        try:
            local=datetime.strptime(raw,fmt)
            if fmt=='%d/%m/%Y':
                local=local.replace(hour=23,minute=59,second=59)
            return local.replace(tzinfo=CLUTCH_TZ).astimezone(timezone.utc)
        except ValueError:
            pass
    raise ValueError('Trade Lock inválido. Use DD/MM/AAAA HH:MM ou DD/MM/AAAA.')

def trade_lock_display(dt):
    dt=utc_aware(dt)
    return dt.astimezone(CLUTCH_TZ).strftime('%d/%m/%Y %H:%M') if dt else '—'

from .config import *
from .db import init_db,Session
from .models import Skin,Panel,Buylist,Interest,Order,Feedback,Ledger,Sale,Operation,Negotiation,NegotiationOrder,TradeInItem,NegotiationPayment,Audit
from .services import *
intents=discord.Intents.default(); intents.members=True
bot=commands.Bot(command_prefix='!',intents=intents)
def gid(i):return i.guild.id if i.guild else (GUILD_ID or 0)

def canonical_order_guild(requested=0):
    return int(GUILD_ID or requested or 0)

def normalize_order_code(code):
    return (code or '').strip().upper()

def find_order_by_code(code, requested_guild=0):
    code=normalize_order_code(code); cg=canonical_order_guild(requested_guild)
    with Session() as s:
        o=s.scalar(select(Order).where(Order.guild_id==cg,Order.code==code))
        if not o:
            o=s.scalar(select(Order).where(Order.code==code))
            if o: print(f'[ORDER RESOLVE] fallback code={code} requested_guild={requested_guild} canonical_guild={cg} found_guild={o.guild_id}')
        if not o: print(f'[ORDER RESOLVE] NOT FOUND code={code} requested_guild={requested_guild} canonical_guild={cg}')
        return o
def money(v):return 'R$ '+f'{D(v):,.2f}'.replace(',','X').replace('.',',').replace('X','.')
def reservation_display(dt):
    dt=utc_aware(dt)
    return dt.astimezone(CLUTCH_TZ).strftime('%d/%m/%Y %H:%M') if dt else '—'
def staff(m):return m.guild_permissions.manage_guild or (STAFF_ROLE_ID and any(r.id==STAFF_ROLE_ID for r in m.roles))
def channel(g,key):
    x=cfg(g,key+'_channel_id');return bot.get_channel(int(x)) if x else None

PUBLIC_CHANNEL_KEYS=('catalog','buylist','interest','order','feedback','news','sold')

def buylist_enabled():
    return (os.getenv('BUYLIST_ENABLED','false') or 'false').strip().lower() in ('1','true','yes','on','sim')

def public_channel_keys():
    return tuple(k for k in PUBLIC_CHANNEL_KEYS if k!='buylist' or buylist_enabled())

def customer_role(guild_id):
    rid=cfg(guild_id,'customer_role_id')
    guild=bot.get_guild(int(guild_id))
    return guild.get_role(int(rid)) if guild and rid else None

async def ensure_negotiation_ticket(guild_id:int,user_id:int,code:str,kind:str,title:str,description:str):
    """Create/reuse one private Discord ticket for a negotiation. Never creates a second business operation."""
    guild=bot.get_guild(int(guild_id))
    if not guild:return None
    key=f'ticket_channel_{code.upper()}'
    existing=cfg(guild_id,key)
    if existing:
        ch=guild.get_channel(int(existing))
        if isinstance(ch,discord.TextChannel):return ch
    member=guild.get_member(int(user_id))
    if member is None:
        try:member=await guild.fetch_member(int(user_id))
        except:return None
    cat=None
    cat_id=cfg(guild_id,'tickets_category_id')
    if cat_id:cat=guild.get_channel(int(cat_id))
    if not isinstance(cat,discord.CategoryChannel):
        cat=discord.utils.get(guild.categories,name='NEGOCIAÇÕES')
    if not isinstance(cat,discord.CategoryChannel):
        try:
            cat=await guild.create_category('NEGOCIAÇÕES',reason='Clutch OS - tickets privados')
            set_cfg(guild_id,'tickets_category_id',cat.id)
        except Exception as e:
            print(f'[TICKET] categoria: {type(e).__name__}: {e}');return None
    overwrites={guild.default_role:discord.PermissionOverwrite(view_channel=False),member:discord.PermissionOverwrite(view_channel=True,send_messages=True,read_message_history=True)}
    if guild.me:overwrites[guild.me]=discord.PermissionOverwrite(view_channel=True,send_messages=True,read_message_history=True,manage_channels=True)
    for role in guild.roles:
        if role.is_default():continue
        if role.permissions.administrator or role.permissions.manage_guild:
            overwrites[role]=discord.PermissionOverwrite(view_channel=True,send_messages=True,read_message_history=True)
    safe=code.lower().replace('_','-')
    emoji={'SALE':'🛒','ORDER':'📦','BUYLIST':'💰'}.get(kind,'🎫')
    try:
        ch=await guild.create_text_channel(f'{emoji}・{safe}',category=cat,overwrites=overwrites,reason=f'Clutch OS ticket {code}')
        set_cfg(guild_id,key,ch.id)
        e=discord.Embed(title=title,description=description,color={'SALE':0x57F287,'ORDER':0x5865F2,'BUYLIST':0xFEE75C}.get(kind,0x5865F2))
        e.add_field(name='Negociação',value=f'`{code}`');e.add_field(name='Cliente',value=member.mention)
        e.set_footer(text='CLUTCH CLUB • atendimento privado e verificado')
        await ch.send(content=member.mention,embed=e)
        print(f'[TICKET] {code} -> #{ch.name} ({ch.id})')
        return ch
    except Exception as e:
        print(f'[TICKET] {code}: {type(e).__name__}: {e}');return None

async def ticket_notice(guild_id:int,code:str,text:str,view=None):
    cid=cfg(guild_id,f'ticket_channel_{code.upper()}')
    if not cid:return False
    ch=bot.get_channel(int(cid))
    if not isinstance(ch,discord.TextChannel):return False
    try:await ch.send(text,view=view);return True
    except Exception as e:print(f'[TICKET] aviso {code}: {type(e).__name__}: {e}');return False

async def close_negotiation_ticket(guild_id:int,code:str,reason='Negociação encerrada'):
    cid=cfg(guild_id,f'ticket_channel_{code.upper()}')
    ch=bot.get_channel(int(cid)) if cid else None
    if not isinstance(ch,discord.TextChannel):return
    try:
        await ch.send(f'🔒 **{reason}.** Este ticket foi arquivado e permanece disponível para histórico.')
        await ch.edit(name=f'🔒・{code.lower()}',reason=f'Clutch OS - {reason}')
        member_id=None
        with Session() as s:
            if code.startswith('VD-'):
                x=s.scalar(select(Sale).where(Sale.guild_id==guild_id,Sale.code==code));member_id=x.buyer_id if x else None
            elif code.startswith('ENC-'):
                x=s.scalar(select(Order).where(Order.guild_id==guild_id,Order.code==code));member_id=x.user_id if x else None
            elif code.startswith('BL-'):
                x=s.scalar(select(Buylist).where(Buylist.guild_id==guild_id,Buylist.code==code));member_id=x.user_id if x else None
        if member_id:
            m=ch.guild.get_member(int(member_id))
            if m:await ch.set_permissions(m,view_channel=True,send_messages=False,read_message_history=True,reason='Negociação encerrada')
    except Exception as e:print(f'[TICKET] fechar {code}: {type(e).__name__}: {e}')

async def notify_operations_event(o, title, text, color=0x5865F2):
    """Make customer proposal decisions visible to staff immediately."""
    ch=channel(o.guild_id,'operations')
    if not isinstance(ch,discord.TextChannel):
        return False
    try:
        e=discord.Embed(title=title,description=text,color=color)
        e.add_field(name='Encomenda',value=f'`{o.code}`')
        e.add_field(name='Cliente',value=f'<@{o.user_id}>')
        if o.customer_price is not None:
            e.add_field(name='Proposta',value=money(o.customer_price))
        e.set_footer(text='CLUTCH OS • PROPOSAL FEEDBACK')
        await ch.send(embed=e)
        return True
    except Exception as exc:
        print(f'[OPERATIONS] falha ao notificar decisão de proposta {o.code}: {type(exc).__name__}: {exc}')
        return False

def customer_access_state(guild_id):
    """Read the effective customer access matrix without changing Discord."""
    role=customer_role(guild_id)
    guild=bot.get_guild(int(guild_id))
    if not guild or not role:
        return False, ['cargo Cliente não configurado/encontrado'], []
    problems=[]; rows=[]
    targets=[(key,channel(guild_id,key),True) for key in public_channel_keys()]
    targets.append(('operations',channel(guild_id,'operations'),False))
    wid=cfg(guild_id,'welcome_channel_id')
    welcome=bot.get_channel(int(wid)) if wid else None
    targets.append(('onboarding',welcome,True))
    seen=set()
    for key,ch,expected in targets:
        if not isinstance(ch,discord.TextChannel):
            continue
        # The welcome channel may also be one of the configured public channels.
        marker=(ch.id,expected)
        if marker in seen: continue
        seen.add(marker)
        actual=bool(ch.permissions_for(role).view_channel)
        rows.append((key,ch,expected,actual))
        if actual != expected:
            problems.append(f'{key}: Cliente {"NÃO VÊ" if not actual else "VÊ"}; esperado {"VÊ" if expected else "NÃO VÊ"}')
    return not problems,problems,rows

async def repair_customer_access(guild_id):
    """V3.7.3: state-aware repair. Writes only when effective access is wrong, then verifies again."""
    guild=bot.get_guild(int(guild_id)); role=customer_role(guild_id)
    if not guild or not role:
        return False,['cargo Cliente não configurado/encontrado']
    ok,_,rows=customer_access_state(guild_id)
    if ok:
        return True,[]
    failures=[]
    for key,ch,expected,actual in rows:
        if actual == expected:
            continue
        try:
            current=ch.overwrites_for(role)
            current.view_channel=expected
            if expected:
                current.read_message_history=True
            await ch.set_permissions(role,overwrite=current,reason='Clutch OS V3.7.3 - corrigir acesso Cliente')
            print(f'[ACCESS] corrigido {key} #{ch.name}: Cliente view_channel={expected}')
        except discord.Forbidden as exc:
            failures.append(f'{key} #{ch.name}: 403 Forbidden ao editar overwrite ({exc})')
        except discord.HTTPException as exc:
            failures.append(f'{key} #{ch.name}: HTTP {getattr(exc,"status","?")} ao editar overwrite ({exc})')
        except Exception as exc:
            failures.append(f'{key} #{ch.name}: {type(exc).__name__} ao editar overwrite ({exc})')
    final_ok,final_problems,_=customer_access_state(guild_id)
    if final_ok:
        return True,[]
    # Report exact write failures plus any state that remains wrong.
    details=failures[:]
    for item in final_problems:
        if item not in details: details.append(item)
    return False,details

def _overwrite_view_value(overwrite):
    """Return an explicit view_channel overwrite as ALLOW/DENY/inherit."""
    value=overwrite.view_channel
    if value is True: return 'ALLOW'
    if value is False: return 'DENY'
    return 'inherit'

def member_access_details(member:discord.Member, ch:discord.TextChannel):
    """Read effective member access and the view_channel overwrite chain. Diagnostic only."""
    effective=bool(ch.permissions_for(member).view_channel)
    everyone=ch.overwrites_for(ch.guild.default_role)
    role_rows=[]
    for role in member.roles:
        if role.is_default():
            continue
        ov=ch.overwrites_for(role)
        if ov.view_channel is not None:
            role_rows.append(f'{role.name}={_overwrite_view_value(ov)}')
    member_ov=ch.overwrites_for(member)
    return {
        'effective': effective,
        'everyone': _overwrite_view_value(everyone),
        'roles': role_rows,
        'member': _overwrite_view_value(member_ov),
        'administrator': bool(member.guild_permissions.administrator),
    }

def log_customer_member_access(guild_id):
    """V3.8.2: log effective access for every real member carrying the Cliente role. No writes."""
    guild=bot.get_guild(int(guild_id)); role=customer_role(guild_id)
    if not guild or not role:
        return
    members=[m for m in guild.members if not m.bot and role in m.roles]
    if not members:
        print('[ACCESS MEMBER] nenhum membro real com cargo Cliente encontrado no cache.')
        return
    targets=[(key,channel(guild_id,key),True) for key in public_channel_keys()]
    wid=cfg(guild_id,'welcome_channel_id')
    welcome=bot.get_channel(int(wid)) if wid else None
    targets.append(('onboarding',welcome,True))
    targets.append(('operations',channel(guild_id,'operations'),False))
    for member in members:
        print(f'[ACCESS MEMBER] {member} ({member.id}) roles={[r.name for r in member.roles if not r.is_default()]}')
        seen=set()
        for key,ch,expected in targets:
            if not isinstance(ch,discord.TextChannel) or ch.id in seen:
                continue
            seen.add(ch.id)
            d=member_access_details(member,ch)
            state='VÊ' if d['effective'] else 'NÃO VÊ'
            # Operations is intentionally visible to administrators/staff.
            expected_for_member = expected
            if key == 'operations' and (d['administrator'] or any(r.name in ('🛡️ Staff','👑 Fundador','Staff','Fundador') for r in member.roles)):
                expected_for_member = True
            verdict='OK' if d['effective']==expected_for_member else 'ERRO'
            print(f'[ACCESS MEMBER]   {key} #{ch.name}: {state} [{verdict}] @everyone={d["everyone"]} roles={d["roles"] or ["inherit"]} member={d["member"]} admin={d["administrator"]}')


async def apply_buylist_mode(guild_id:int):
    """Apply the logical buylist mode without changing Discord permissions.

    BUYLIST_ENABLED controls backend acceptance, public panel state and shortcuts.
    Channel visibility is intentionally left to Discord configuration so startup never
    requires Manage Channels/Manage Roles and cannot fail with 403 Missing Permissions.
    History/data are never deleted.
    """
    print('[VERSION] CLUTCH OS V3.8.4.9 — RESERVED RECOVERY FIX')
    guild=bot.get_guild(int(guild_id)); ch=channel(guild_id,'buylist')
    if not guild or not isinstance(ch,discord.TextChannel):
        print('[BUYLIST MODE] canal buylist não encontrado; modo lógico preservado.')
        return False
    enabled=buylist_enabled()
    print(f'[BUYLIST MODE] {"ATIVA" if enabled else "PAUSADA"} | backend={"liberado" if enabled else "bloqueado"} | permissões Discord não alteradas | histórico preservado')
    return True

def operation_embed(op):
    colors={'BUYLIST':0xFEE75C,'ORDER':0x5865F2,'SALE':0x57F287,'COUNTER':0xEB459E,'PAYMENT':0x57F287,'MATCH':0x9B59B6,'TRADEIN':0xF1C40F}
    e=discord.Embed(title=f'📟 {op.title}',description=op.detail or 'Pendência operacional',color=colors.get(op.kind,0x2B2D31))
    e.add_field(name='Código',value=f'`{op.ref_code}`')
    e.add_field(name='Tipo',value=op.kind)
    e.add_field(name='Status',value=op.status)
    if op.user_id:e.add_field(name='Cliente',value=f'<@{op.user_id}>',inline=False)
    if op.assigned_to:e.add_field(name='Responsável',value=f'<@{op.assigned_to}>',inline=False)
    e.add_field(name='Prioridade',value=op.priority)
    e.set_footer(text='CLUTCH OS • OPERATIONS CENTER')
    return e

def queue_operation(guild_id,kind,ref_code,entity_id,user_id,title,detail='',priority='NORMAL'):
    with Session.begin() as s:
        existing=s.scalar(select(Operation).where(Operation.guild_id==guild_id,Operation.kind==kind,Operation.ref_code==ref_code,Operation.status.in_(['OPEN','WAITING','ACTION_REQUIRED'])))
        if existing:
            existing.title=title;existing.detail=detail;existing.priority=priority;return existing.id
        op=Operation(guild_id=guild_id,kind=kind,ref_code=ref_code,entity_id=entity_id,user_id=user_id,title=title,detail=detail,status='OPEN',priority=priority);s.add(op);s.flush();return op.id

async def publish_operation(op_id):
    with Session() as s:op=s.get(Operation,op_id)
    if not op:return False
    # Idempotência: se esta operação já possui mensagem operacional, não publica duplicata.
    if op.staff_channel_id and op.staff_message_id:
        ch0=bot.get_channel(int(op.staff_channel_id))
        if isinstance(ch0,discord.TextChannel):
            try:
                await ch0.fetch_message(int(op.staff_message_id))
                return True
            except discord.NotFound:
                pass
            except discord.Forbidden:
                print(f'[OPS] {op.ref_code} já tem vínculo Discord, mas sem acesso para validar mensagem.')
                return True
            except discord.HTTPException:
                return True
    ch=channel(op.guild_id,'operations')
    if not isinstance(ch,discord.TextChannel):
        print(f'[OPS] {op.ref_code} salvo na fila, mas canal operations não configurado.')
        return False
    try:
        m=await ch.send(embed=operation_embed(op),view=OperationsView())
        with Session.begin() as s:
            x=s.get(Operation,op_id);x.staff_channel_id=ch.id;x.staff_message_id=m.id
        print(f'[OPS] {op.ref_code} publicado em #{ch.name} ({ch.id}) mensagem {m.id}.')
        return True
    except Exception as e:
        print(f'[OPS] Falha ao publicar {op.ref_code}: {type(e).__name__}: {e}')
        return False

async def resolve_operation_by_message(interaction,new_status):
    with Session.begin() as s:
        op=s.scalar(select(Operation).where(Operation.guild_id==gid(interaction),Operation.staff_message_id==interaction.message.id).with_for_update())
        if not op:return None
        op.status=new_status
        if new_status=='ACTION_REQUIRED': op.assigned_to=interaction.user.id
        log(s,gid(interaction),interaction.user.id,'OPERATION_STATUS','operation',op.id,f'{op.ref_code} -> {new_status}');oid=op.id
    with Session() as s:op=s.get(Operation,oid)
    try:await interaction.message.edit(embed=operation_embed(op),view=OperationsView() if new_status not in ('DONE','CANCELLED') else None)
    except:pass
    return op
def skin_embed(x):
    e=discord.Embed(title=x.name,description=f'**{x.code}** • {x.status}',color=0x57F287 if x.status=='AVAILABLE' else 0xFEE75C);e.add_field(name='Exterior',value=x.exterior or '—');e.add_field(name='Float',value=x.floatv or '—');e.add_field(name='Pattern',value=x.pattern or '—');e.add_field(name='💰 Preço',value=money(x.price),inline=False)
    if x.inspect:e.add_field(name='🔍 Inspect',value=x.inspect[:1000],inline=False)
    if x.image_url:e.set_image(url=x.image_url)
    e.set_footer(text='CLUTCH CLUB • PLAY • TRADE • EVOLVE');return e

class BuyModal(discord.ui.Modal,title='Vender uma skin'):
    skin=discord.ui.TextInput(label='Skin',placeholder='AK-47 | Redline');exterior=discord.ui.TextInput(label='Exterior',placeholder='FN / MW / FT / WW / BS');floatv=discord.ui.TextInput(label='Float',placeholder='0.135');desired=discord.ui.TextInput(label='Valor desejado',placeholder='205,00');extra=discord.ui.TextInput(label='Pattern / stickers / observações',required=False,style=discord.TextStyle.paragraph)
    async def on_submit(self,i):
        if not buylist_enabled():
            return await i.response.send_message('⏸️ A compra de skins pela Clutch Club está temporariamente pausada. Você ainda pode **comprar**, **encomendar** ou entrar na **lista de interesse**.',ephemeral=True)
        if not valid_float(self.floatv.value):return await i.response.send_message('❌ Float inválido. Use 0 a 1.',ephemeral=True)
        try:d=D(self.desired.value)
        except:return await i.response.send_message('❌ Valor inválido.',ephemeral=True)
        with Session.begin() as s:
            b=Buylist(code='PENDING',guild_id=gid(i),user_id=i.user.id,skin_name=self.skin.value,exterior=self.exterior.value.upper(),floatv=self.floatv.value.replace(',','.'),pattern=self.extra.value[:120] or None,desired_price=d,status='PENDING');s.add(b);s.flush();b.code=f'BL-{b.id:05d}';log(s,gid(i),i.user.id,'BUYLIST_CREATE','buylist',b.id,b.skin_name)
        opid=queue_operation(gid(i),'BUYLIST',b.code,b.id,i.user.id,f'BUYLIST — {b.code}',f'**Skin:** {b.skin_name}\n**Exterior:** {b.exterior}\n**Float:** {b.floatv}\n**Desejado:** {money(d)}','HIGH')
        await publish_operation(opid)
        await ensure_negotiation_ticket(gid(i),i.user.id,b.code,'BUYLIST',f'💰 BUYLIST — {b.code}',f'**Skin:** {b.skin_name}\n**Exterior:** {b.exterior}\n**Float:** {b.floatv}\n**Valor desejado:** {money(d)}\n\nUse este canal para acompanhar toda a negociação com a equipe.')
        await i.response.send_message(f'✅ **{b.code}** criada por {money(d)}. Seu ticket privado foi aberto e a equipe foi notificada.',ephemeral=True)

def _code_from_interaction_message(i, prefix):
    import re
    parts=[]
    if getattr(i,'message',None):
        if i.message.content: parts.append(i.message.content)
        for e in i.message.embeds:
            parts.extend([e.title or '',e.description or ''])
    m=re.search(rf'\b{prefix}-\d{{5}}\b','\n'.join(parts),re.I)
    return m.group(0).upper() if m else None

class AcceptModal(discord.ui.Modal,title='Responder proposta'):
    def __init__(self,code:str):
        super().__init__();self.code=code.upper()
    async def on_submit(self,i):
        with Session.begin() as s:
            b=s.scalar(select(Buylist).where(Buylist.guild_id==gid(i),Buylist.code==self.code,Buylist.user_id==i.user.id).with_for_update())
            if not b or b.status!='PROPOSED':return await i.response.send_message('❌ Não há proposta ativa para essa Buylist.',ephemeral=True)
            if b.proposal_expires_at and utc_aware(b.proposal_expires_at) < datetime.now(timezone.utc):b.status='EXPIRED';return await i.response.send_message('⌛ Essa proposta expirou.',ephemeral=True)
            b.status='ACCEPTED';proposal=b.proposal;code=b.code
            op=s.scalar(select(Operation).where(Operation.guild_id==gid(i),Operation.kind=='BUYLIST',Operation.ref_code==b.code,Operation.status.in_(['OPEN','WAITING','ACTION_REQUIRED'])).with_for_update())
            if op:op.status='ACTION_REQUIRED'
            log(s,gid(i),i.user.id,'BUYLIST_ACCEPT','buylist',b.id,str(b.proposal))
        await refresh_buylist_operation(code,gid(i))
        await i.response.send_message(f'✅ Proposta de **{money(proposal)}** aceita. A equipe foi avisada para receber a skin.',ephemeral=True)

class CounterModal(discord.ui.Modal,title='Fazer contraproposta'):
    value=discord.ui.TextInput(label='Sua contraproposta',placeholder='170,00')
    def __init__(self,code:str):
        super().__init__();self.code=code.upper()
    async def on_submit(self,i):
        try:v=D(self.value.value)
        except:return await i.response.send_message('❌ Valor inválido.',ephemeral=True)
        with Session.begin() as s:
            b=s.scalar(select(Buylist).where(Buylist.guild_id==gid(i),Buylist.code==self.code,Buylist.user_id==i.user.id).with_for_update())
            if not b or b.status!='PROPOSED':return await i.response.send_message('❌ Não há proposta ativa.',ephemeral=True)
            b.counterproposal=v;b.status='COUNTERED';code=b.code
            op=s.scalar(select(Operation).where(Operation.guild_id==gid(i),Operation.kind=='BUYLIST',Operation.ref_code==b.code).order_by(Operation.id.desc()).with_for_update())
            if op:
                op.status='ACTION_REQUIRED';op.title=f'BUYLIST — {b.code}'
                op.detail=f'**Skin:** {b.skin_name}\n**Desejado:** {money(b.desired_price)}\n**Última proposta Clutch:** {money(b.proposal)}\n**Contraproposta do cliente:** {money(v)}\n\n➡️ Use **AÇÃO / PRÓXIMA ETAPA** para responder na mesma negociação.'
            log(s,gid(i),i.user.id,'BUYLIST_COUNTER','buylist',b.id,str(v))
        await refresh_buylist_operation(code,gid(i))
        await i.response.send_message(f'🔄 Contraproposta de **{money(v)}** enviada. A negociação continua na **{code}**.',ephemeral=True)

class ReserveModal(discord.ui.Modal,title='Comprar / reservar skin'):
    code=discord.ui.TextInput(label='Código da skin',placeholder='SK-00001')
    async def on_submit(self,i):
        try:sale,x=reserve(gid(i),i.user.id,self.code.value,RESERVATION_MINUTES)
        except Exception as e:return await i.response.send_message(f'❌ {e}',ephemeral=True)
        await refresh_skin(x.id);expires=reservation_display(sale.reserved_until);opid=queue_operation(gid(i),'SALE',sale.code,sale.id,i.user.id,f'RESERVA / VENDA — {sale.code}',f'**Skin:** {x.code} • {x.name}\n**Valor:** {money(sale.sale_price)}\n**Reserva expira:** {expires}\n\n⏱️ Se o pagamento não for confirmado até esse horário, a reserva será cancelada automaticamente.','HIGH');await publish_operation(opid);await i.response.send_message(f'🔒 **{x.code}** reservada até **{expires}**. Pedido **{sale.code}**, valor **{money(sale.sale_price)}**. A equipe já foi notificada.',ephemeral=True)

class InterestModal(discord.ui.Modal,title='Lista de interesse'):
    skin=discord.ui.TextInput(label='Skin procurada');exterior=discord.ui.TextInput(label='Exterior',required=False);budget=discord.ui.TextInput(label='Orçamento máximo',required=False);maxfloat=discord.ui.TextInput(label='Float máximo',required=False)
    async def on_submit(self,i):
        if self.maxfloat.value and not valid_float(self.maxfloat.value):return await i.response.send_message('❌ Float máximo inválido.',ephemeral=True)
        try:b=D(self.budget.value) if self.budget.value else None
        except:return await i.response.send_message('❌ Orçamento inválido.',ephemeral=True)
        with Session.begin() as s:s.add(Interest(guild_id=gid(i),user_id=i.user.id,skin_name=self.skin.value,exterior=self.exterior.value.upper() or None,max_budget=b,max_float=self.maxfloat.value or None))
        await i.response.send_message('🔔 Interesse salvo. Avisaremos quando houver match.',ephemeral=True)

class OrderModal(discord.ui.Modal,title='Encomendar uma skin'):
    skin=discord.ui.TextInput(label='Skin procurada');exterior=discord.ui.TextInput(label='Exterior',required=False);maxfloat=discord.ui.TextInput(label='Float máximo',required=False);budget=discord.ui.TextInput(label='Orçamento máximo',required=False);notes=discord.ui.TextInput(label='Observações',required=False,style=discord.TextStyle.paragraph)
    async def on_submit(self,i):
        if self.maxfloat.value and not valid_float(self.maxfloat.value):return await i.response.send_message('❌ Float inválido.',ephemeral=True)
        from clutch_os.core.orders import OrderService
        result=OrderService.create(gid(i),i.user.id,getattr(i.user,'display_name',None) or str(i.user),self.skin.value,self.exterior.value,self.maxfloat.value,self.budget.value,self.notes.value)
        oid=result['order_id'];ocode=result['code'];opid=result['operation_id']
        published=await publish_operation(opid)
        await ensure_negotiation_ticket(gid(i),i.user.id,ocode,'ORDER',f'📦 ENCOMENDA — {ocode}',f'**Skin:** {self.skin.value}\n**Exterior:** {self.exterior.value.upper() or "—"}\n**Float máximo:** {self.maxfloat.value or "—"}\n**Orçamento:** {money(D(self.budget.value)) if self.budget.value else "—"}\n\nA equipe acompanhará sua encomenda por este canal.')
        e=discord.Embed(title=f'📦 ENCOMENDA {ocode} REGISTRADA',description='Confira abaixo exatamente o que você pediu.',color=0x5865F2)
        e.add_field(name='Skin',value=self.skin.value,inline=False);e.add_field(name='Exterior',value=self.exterior.value.upper() or '—');e.add_field(name='Float máximo',value=self.maxfloat.value or '—');e.add_field(name='Orçamento máximo',value=money(D(self.budget.value)) if self.budget.value else '—');e.add_field(name='Observações',value=self.notes.value or '—',inline=False);e.add_field(name='Status',value='🟡 ABERTA / AGUARDANDO ANÁLISE',inline=False)
        e.set_footer(text='A equipe foi notificada. Não envie pagamento antes de uma proposta oficial da Clutch Club.')
        await i.response.send_message(embed=e,view=OrderCustomerView(),ephemeral=True)

ORDER_FLOW=['OPEN','SEARCHING','FOUND','PROPOSAL_SENT','CUSTOMER_ACCEPTED','PAYMENT_PENDING','PAYMENT_CONFIRMED','AWAITING_ACQUISITION','ACQUIRED','TRADE_LOCK','READY','DELIVERED']
ORDER_LABELS={'OPEN':'ABERTA','SEARCHING':'PROCURANDO','FOUND':'SKIN ENCONTRADA','PROPOSAL_SENT':'PROPOSTA AO CLIENTE','CUSTOMER_ACCEPTED':'CLIENTE ACEITOU','PAYMENT_PENDING':'PAGAMENTO PENDENTE','PAYMENT_CONFIRMED':'PAGAMENTO CONFIRMADO','AWAITING_ACQUISITION':'AGUARDANDO AQUISIÇÃO','ACQUIRED':'ADQUIRIDA','TRADE_LOCK':'TRADE LOCK','READY':'PRONTA PARA ENTREGA','DELIVERED':'ENTREGUE','CANCELLED':'CANCELADA'}
def order_status_label(v):return ORDER_LABELS.get(v,v)
def finalize_order_financials(guild, actor, order):
    """Post the financial result of a delivered order exactly once.

    Orders are direct procurement transactions, not inventory Sale rows.  Their
    cash events therefore live in Ledger and are keyed by order code.
    """
    if order.customer_price is None or order.found_price is None:
        raise ValueError('Para entregar, a encomenda precisa ter custo encontrado e preço ao cliente.')
    with Session.begin() as s:
        o=s.scalar(select(Order).where(Order.guild_id==guild,Order.id==order.id).with_for_update())
        if not o: raise ValueError('Encomenda não encontrada ao fechar financeiro.')
        # Idempotency: retries/restarts must never duplicate cash movements.
        sale_note=f'{o.code}:ORDER_SALE'
        cost_note=f'{o.code}:ORDER_COST'
        has_sale=s.scalar(select(Ledger.id).where(Ledger.guild_id==guild,Ledger.kind=='ORDER_SALE',Ledger.note==sale_note).limit(1))
        has_cost=s.scalar(select(Ledger.id).where(Ledger.guild_id==guild,Ledger.kind=='ORDER_COST',Ledger.note==cost_note).limit(1))
        if not has_cost:
            s.add(Ledger(guild_id=guild,kind='ORDER_COST',amount=-D(o.found_price),note=cost_note))
        if not has_sale:
            s.add(Ledger(guild_id=guild,kind='ORDER_SALE',amount=D(o.customer_price),note=sale_note))
        if not has_sale or not has_cost:
            log(s,guild,actor,'ORDER_FINANCIAL_CLOSE','order',o.id,f'{o.code}; cost={o.found_price}; revenue={o.customer_price}')

def advance_order(guild,actor,code,target=None):
    code=normalize_order_code(code); cg=canonical_order_guild(guild)
    with Session.begin() as s:
        o=s.scalar(select(Order).where(Order.guild_id==cg,Order.code==code).with_for_update())
        if not o:
            o=s.scalar(select(Order).where(Order.code==code).with_for_update())
            if o: print(f'[ORDER RESOLVE] advance fallback code={code} requested_guild={guild} canonical_guild={cg} found_guild={o.guild_id}')
        if not o:
            print(f'[ORDER RESOLVE] advance NOT FOUND code={code} requested_guild={guild} canonical_guild={cg}')
            raise ValueError('Encomenda não encontrada.')
        if o.status in ('DELIVERED','CANCELLED'):raise ValueError('Encomenda já encerrada.')
        if target:
            if target not in ORDER_FLOW and target!='CANCELLED':raise ValueError('Status inválido.')
            nxt=target
        else:
            try:nxt=ORDER_FLOW[ORDER_FLOW.index(o.status)+1]
            except (ValueError,IndexError):raise ValueError('Não existe próxima etapa.')
        o.status=nxt
        if not o.assigned_to:o.assigned_to=actor
        log(s,o.guild_id,actor,'ORDER_STATUS','order',o.id,f'{code} -> {nxt}')
        return o
async def notify_order_customer(o):
    public={'SEARCHING':'🔎 Nossa equipe começou a procurar sua skin.','FOUND':'🎯 Encontramos uma opção compatível. A equipe está preparando os detalhes.','PROPOSAL_SENT':'💰 Uma proposta oficial foi preparada para sua encomenda.','CUSTOMER_ACCEPTED':'🤝 Sua proposta foi marcada como aceita.','PAYMENT_PENDING':'💳 Aguardando a confirmação do pagamento.','PAYMENT_CONFIRMED':'✅ Pagamento confirmado. A equipe seguirá com a aquisição.','AWAITING_ACQUISITION':'🛒 Estamos aguardando/finalizando a aquisição da skin.','ACQUIRED':'✅ A skin foi adquirida pela Clutch Club.','TRADE_LOCK':f'🔒 A skin está em Trade Lock'+(f' até {trade_lock_display(o.trade_lock_until)}' if o.trade_lock_until else '')+'.','READY':'📦 Sua skin está pronta para entrega.','DELIVERED':'🎉 Encomenda entregue. Obrigado por negociar com a Clutch Club!','CANCELLED':'❌ Sua encomenda foi cancelada.'}
    msg=public.get(o.status)
    if not msg:return
    await ticket_notice(o.guild_id,o.code,f'**📦 {o.code} — {order_status_label(o.status)}**\n{msg}')
    try:
        u=bot.get_user(o.user_id) or await bot.fetch_user(o.user_id);await u.send(f'**📦 {o.code} — {order_status_label(o.status)}**\n{msg}')
    except:pass
    if o.status in ('DELIVERED','CANCELLED'):await close_negotiation_ticket(o.guild_id,o.code,'Encomenda encerrada')
async def sync_order_operation(o):
    with Session.begin() as s:
        op=s.scalar(select(Operation).where(Operation.guild_id==o.guild_id,Operation.kind=='ORDER',Operation.ref_code==o.code).order_by(Operation.id.desc()).with_for_update())
        if not op:return
        op.status='DONE' if o.status in ('DELIVERED','CANCELLED') else 'ACTION_REQUIRED';op.assigned_to=o.assigned_to
        op.detail=f'**Skin:** {o.skin_name}\n**Exterior:** {o.exterior or "—"}\n**Float máx.:** {o.max_float or "—"}\n**Orçamento:** {money(o.budget) if o.budget is not None else "—"}\n**Status da encomenda:** **{order_status_label(o.status)}**\n**Custo encontrado:** {money(o.found_price) if o.found_price is not None else "—"}\n**Preço ao cliente:** {money(o.customer_price) if o.customer_price is not None else "—"}\n**Float encontrado:** {o.found_float or "—"}\n**Fornecedor:** {o.supplier or "—"}\n**Listing:** {o.listing_url or "—"}\n**Inspect:** {o.inspect_link or "—"}\n**Observações:** {o.notes or "—"}'
        oid=op.id;cid=op.staff_channel_id;mid=op.staff_message_id
    if cid and mid:
        try:
            ch=bot.get_channel(cid);m=await ch.fetch_message(mid)
            with Session() as s:op=s.get(Operation,oid)
            await m.edit(embed=operation_embed(op),view=None if op.status=='DONE' else OperationsView())
        except:pass

class OrderPaidNoticeView(discord.ui.View):
    def __init__(self,guild_id:int,order_id:int,code:str,payment_url:str|None=None):
        super().__init__(timeout=86400)
        self.guild_id=int(guild_id); self.order_id=int(order_id); self.code=code
        if payment_url:
            self.add_item(discord.ui.Button(label='ABRIR PAGAMENTO SEGURO',emoji='💳',style=discord.ButtonStyle.link,url=payment_url))
    @discord.ui.button(label='JÁ FIZ O PAGAMENTO',emoji='✅',style=discord.ButtonStyle.success)
    async def paid(self,i,b):
        with Session() as s:o=s.scalar(select(Order).where(Order.id==self.order_id,Order.guild_id==self.guild_id,Order.code==self.code,Order.user_id==i.user.id))
        if not o:return await i.response.send_message('❌ Encomenda não encontrada.',ephemeral=True)
        if o.status!='PAYMENT_PENDING':return await i.response.send_message('ℹ️ Esta encomenda não está aguardando pagamento.',ephemeral=True)
        await i.response.defer(ephemeral=True)
        method=cfg(self.guild_id,f'order_payment_method_{o.id}','PIX')
        await notify_operations_event(o,f'💰 {o.code} — CLIENTE INFORMOU PAGAMENTO',f'<@{o.user_id}> informou que realizou o pagamento por **{method}**.\n⚠️ Confira o recebimento antes de confirmar.',0xFEE75C)
        await i.followup.send('✅ Avisamos a equipe. O pagamento será confirmado somente após a conferência do recebimento.',ephemeral=True)
        try: await i.message.edit(view=None)
        except: pass

class OrderPaymentMethodView(discord.ui.View):
    def __init__(self,guild_id:int,order_id:int,code:str):
        super().__init__(timeout=86400)
        self.guild_id=int(guild_id); self.order_id=int(order_id); self.code=code
    def _load(self,user_id):
        with Session() as s:return s.scalar(select(Order).where(Order.id==self.order_id,Order.guild_id==self.guild_id,Order.code==self.code,Order.user_id==user_id))
    async def _choose(self,i,method):
        o=self._load(i.user.id)
        if not o:return await i.response.send_message('❌ Encomenda não encontrada.',ephemeral=True)
        if o.status not in ('CUSTOMER_ACCEPTED','PAYMENT_PENDING'):return await i.response.send_message(f'ℹ️ Esta encomenda está em **{order_status_label(o.status)}**.',ephemeral=True)
        if method=='PIX':
            pix=(cfg(self.guild_id,'pix_key') or '').strip()
            if not pix:
                await notify_operations_event(o,f'⚠️ {o.code} — PIX NÃO CONFIGURADO','O cliente escolheu **PIX**, mas a chave PIX ainda não foi configurada. Use `/configurar-pagamento`.',0xED4245)
                return await i.response.send_message('⚠️ O PIX está temporariamente indisponível. A equipe já foi avisada. Você pode escolher cartão ou aguardar a configuração.',ephemeral=True)
        await i.response.defer(ephemeral=True)
        if o.status=='CUSTOMER_ACCEPTED':o=advance_order(self.guild_id,i.user.id,o.code,'PAYMENT_PENDING')
        set_cfg(self.guild_id,f'order_payment_method_{o.id}',method)
        await sync_order_operation(o); await notify_order_customer(o)
        if method=='PIX':
            pix=cfg(self.guild_id,'pix_key')
            holder=cfg(self.guild_id,'pix_holder','Clutch Club')
            text=f'💠 **PIX — {o.code}**\nValor: **{money(o.customer_price)}**\nChave PIX: `{pix}`\nFavorecido: **{holder}**\n\nApós pagar, guarde o comprovante e clique em **JÁ FIZ O PAGAMENTO**. A equipe conferirá o recebimento antes da aquisição.'
            await i.followup.send(text,view=OrderPaidNoticeView(self.guild_id,o.id,o.code),ephemeral=False)
            await notify_operations_event(o,f'💠 {o.code} — PAGAMENTO VIA PIX',f'<@{o.user_id}> escolheu **PIX**. A chave foi enviada ao cliente. Aguarde a confirmação e confira o recebimento.',0x57F287)
        else:
            await i.followup.send(f'💳 **Cartão de crédito selecionado — {o.code}**\nA equipe foi avisada e enviará aqui o link oficial de pagamento.',ephemeral=False)
            await notify_operations_event(o,f'💳 {o.code} — CLIENTE ESCOLHEU CARTÃO',f'<@{o.user_id}> solicitou pagamento por **cartão de crédito**.\nNo card da operação, clique **AÇÃO / PRÓXIMA ETAPA** para inserir o link de pagamento.',0x5865F2)
        try: await i.message.edit(view=None)
        except: pass
    @discord.ui.button(label='PIX',emoji='💠',style=discord.ButtonStyle.success)
    async def pix(self,i,b):await self._choose(i,'PIX')
    @discord.ui.button(label='CARTÃO DE CRÉDITO',emoji='💳',style=discord.ButtonStyle.primary)
    async def card(self,i,b):await self._choose(i,'CARD')

class CardPaymentLinkModal(discord.ui.Modal,title='Enviar link de pagamento'):
    link=discord.ui.TextInput(label='Link de pagamento',placeholder='https://...',max_length=1000)
    def __init__(self,code):super().__init__();self.code=code
    async def on_submit(self,i):
        raw=str(self.link.value).strip()
        if not (raw.startswith('https://') or raw.startswith('http://')):return await i.response.send_message('❌ Informe um link http:// ou https:// válido.',ephemeral=True)
        with Session() as s:o=s.scalar(select(Order).where(Order.guild_id==gid(i),Order.code==self.code))
        if not o:return await i.response.send_message('❌ Encomenda não encontrada.',ephemeral=True)
        if o.status!='PAYMENT_PENDING':return await i.response.send_message('❌ A encomenda não está aguardando pagamento.',ephemeral=True)
        if cfg(o.guild_id,f'order_payment_method_{o.id}')!='CARD':return await i.response.send_message('❌ O cliente não selecionou cartão nesta encomenda.',ephemeral=True)
        set_cfg(o.guild_id,f'order_payment_link_{o.id}',raw)
        await i.response.defer(ephemeral=True)
        u=bot.get_user(o.user_id) or await bot.fetch_user(o.user_id)
        v=OrderPaidNoticeView(o.guild_id,o.id,o.code,payment_url=raw)
        await u.send(f'💳 **PAGAMENTO POR CARTÃO — {o.code}**\nValor: **{money(o.customer_price)}**\nUse somente o link oficial abaixo. Depois do pagamento, clique em **JÁ FIZ O PAGAMENTO**.',view=v)
        await notify_operations_event(o,f'🔗 {o.code} — LINK DE CARTÃO ENVIADO',f'O link oficial de pagamento foi enviado a <@{o.user_id}>. Aguarde e confira o recebimento antes de confirmar.',0x57F287)
        await i.followup.send(f'✅ Link de pagamento enviado ao cliente da **{o.code}**.',ephemeral=True)

class OrderPaymentStaffView(discord.ui.View):
    def __init__(self,code,method):
        super().__init__(timeout=300);self.code=code;self.method=(method or 'PIX').upper()
        # V3.7.4: o botão de cartão só existe quando o cliente realmente escolheu CARTÃO.
        if self.method=='CARD':
            link_btn=discord.ui.Button(label='ENVIAR LINK DO CARTÃO',emoji='💳',style=discord.ButtonStyle.primary)
            link_btn.callback=self.link
            self.add_item(link_btn)
    @discord.ui.button(label='CONFIRMAR PAGAMENTO',emoji='✅',style=discord.ButtonStyle.success)
    async def confirm(self,i,b):
        if not staff(i.user):return await i.response.send_message('Somente a equipe.',ephemeral=True)
        with Session() as s:o=s.scalar(select(Order).where(Order.guild_id==gid(i),Order.code==self.code))
        if not o:return await i.response.send_message('❌ Encomenda não encontrada.',ephemeral=True)
        if o.status!='PAYMENT_PENDING':return await i.response.send_message('❌ A encomenda não está aguardando pagamento.',ephemeral=True)
        await i.response.defer(ephemeral=True);o=advance_order(gid(i),i.user.id,o.code,'PAYMENT_CONFIRMED');await sync_order_operation(o);await notify_order_customer(o)
        # Card auxiliar resolvido: remove da tela para o Operations Center não virar histórico visual.
        try: await i.message.delete()
        except Exception:
            try: await i.message.edit(view=None)
            except Exception: pass
        await i.followup.send(f'✅ **{o.code}** → PAGAMENTO CONFIRMADO.',ephemeral=True)
    async def link(self,i):
        if not staff(i.user):return await i.response.send_message('Somente a equipe.',ephemeral=True)
        if self.method!='CARD':return await i.response.send_message('ℹ️ Esta encomenda está configurada para PIX.',ephemeral=True)
        await i.response.send_modal(CardPaymentLinkModal(self.code))

class CustomerOrderProposalView(discord.ui.View):
    def __init__(self,guild_id:int,order_id:int,code:str):
        super().__init__(timeout=86400)
        self.guild_id=int(guild_id)
        self.order_id=int(order_id)
        self.code=code

    def _query(self,user_id:int,lock:bool=False):
        # A proposta é respondida por DM, portanto interaction.guild é None.
        # O namespace deve ser o da encomenda original, nunca o da interação.
        q=select(Order).where(
            Order.id==self.order_id,
            Order.guild_id==self.guild_id,
            Order.code==self.code,
            Order.user_id==user_id,
        )
        return q.with_for_update() if lock else q

    async def _load(self,i):
        with Session() as s:
            return s.scalar(self._query(i.user.id))

    @discord.ui.button(label='ACEITAR PROPOSTA',emoji='✅',style=discord.ButtonStyle.success)
    async def accept(self,i,b):
        await i.response.defer(ephemeral=True)
        with Session.begin() as s:
            o=s.scalar(self._query(i.user.id,lock=True))
            if not o:
                return await i.followup.send('❌ Encomenda não encontrada.',ephemeral=True)
            if o.status!='PROPOSAL_SENT':
                return await i.followup.send('❌ Esta proposta não está mais aguardando sua resposta.',ephemeral=True)
            expires=utc_aware(o.proposal_expires_at)
            if expires and expires < datetime.now(timezone.utc):
                o.status='FOUND'
                log(s,self.guild_id,i.user.id,'ORDER_PROPOSAL_EXPIRED','order',o.id,o.code)
                return await i.followup.send('⌛ A proposta expirou. A equipe foi avisada para revisar as condições.',ephemeral=True)
            o.status='CUSTOMER_ACCEPTED'
            o.customer_accepted_at=datetime.now(timezone.utc)
            log(s,self.guild_id,i.user.id,'ORDER_CUSTOMER_ACCEPT','order',o.id,o.code)
            oid=o.id
        with Session() as s:
            o=s.scalar(select(Order).where(Order.id==oid,Order.guild_id==self.guild_id))
        if not o:
            return await i.followup.send('❌ A encomenda foi aceita, mas não pôde ser recarregada. Avise a equipe.',ephemeral=True)
        await sync_order_operation(o)
        await notify_order_customer(o)
        await notify_operations_event(o,f'🟢 {o.code} — CLIENTE ACEITOU',f'<@{o.user_id}> **ACEITOU** a proposta de **{money(o.customer_price)}**.\nPróxima etapa: **ESCOLHER FORMA DE PAGAMENTO**.',0x57F287)
        await i.followup.send(f'✅ Você aceitou a proposta da **{o.code}** por **{money(o.customer_price)}**.\n\nEscolha agora a forma de pagamento:',view=OrderPaymentMethodView(o.guild_id,o.id,o.code),ephemeral=False)
        try: await i.message.edit(view=None)
        except: pass

    @discord.ui.button(label='RECUSAR',emoji='❌',style=discord.ButtonStyle.danger)
    async def reject(self,i,b):
        await i.response.defer(ephemeral=True)
        with Session.begin() as s:
            o=s.scalar(self._query(i.user.id,lock=True))
            if not o:
                return await i.followup.send('❌ Encomenda não encontrada.',ephemeral=True)
            if o.status!='PROPOSAL_SENT':
                return await i.followup.send('❌ Esta proposta não está mais aguardando sua resposta.',ephemeral=True)
            rejected_price=o.customer_price
            o.status='SEARCHING'
            o.customer_price=None
            o.proposal_expires_at=None
            log(s,self.guild_id,i.user.id,'ORDER_CUSTOMER_REJECT','order',o.id,f'{o.code}; rejected_price={rejected_price}')
            oid=o.id
        with Session() as s:
            o=s.scalar(select(Order).where(Order.id==oid,Order.guild_id==self.guild_id))
        if not o:
            return await i.followup.send('❌ A recusa foi registrada, mas a encomenda não pôde ser recarregada. Avise a equipe.',ephemeral=True)
        await sync_order_operation(o)
        shown=money(rejected_price) if rejected_price is not None else '—'
        await notify_operations_event(o,f'🔴 {o.code} — CLIENTE RECUSOU',f'<@{o.user_id}> **RECUSOU** a proposta de **{shown}**.\nA encomenda voltou para **PROCURANDO** para uma nova opção.',0xED4245)
        await i.followup.send('↩️ Proposta recusada. A encomenda voltou para **PROCURANDO**.',ephemeral=True)
        try: await i.message.edit(view=None)
        except: pass

async def send_order_proposal(o):
    if o.found_price is None or o.customer_price is None or not o.supplier:
        raise ValueError('Preencha custo, preço ao cliente e fornecedor antes de enviar a proposta.')
    if o.found_float and not valid_float(o.found_float):raise ValueError('Float encontrado inválido.')
    profit=D(o.customer_price)-D(o.found_price);roi=(profit/D(o.found_price)*100) if D(o.found_price)>0 else D(0)
    e=discord.Embed(title=f'💰 PROPOSTA — {o.code}',description='Encontramos uma opção compatível com sua encomenda.',color=0xFEE75C)
    e.add_field(name='Skin',value=o.skin_name,inline=False);e.add_field(name='Exterior',value=o.exterior or '—');e.add_field(name='Float',value=o.found_float or '—');e.add_field(name='Valor',value=money(o.customer_price));
    if o.inspect_link:e.add_field(name='🔍 Inspect',value=o.inspect_link[:1000],inline=False)
    e.add_field(name='Validade',value=o.proposal_expires_at.strftime('%d/%m/%Y %H:%M') if o.proposal_expires_at else '24 horas',inline=False)
    e.set_footer(text='A aquisição só avança após sua confirmação. Não faça pagamentos fora dos canais oficiais da Clutch Club.')
    u=bot.get_user(o.user_id) or await bot.fetch_user(o.user_id)
    await u.send(embed=e,view=CustomerOrderProposalView(o.guild_id,o.id,o.code))
    return profit,roi

class FoundSkinModal(discord.ui.Modal,title='Registrar skin encontrada'):
    custo=discord.ui.TextInput(label='Custo de aquisição',placeholder='120,00')
    preco=discord.ui.TextInput(label='Preço ao cliente',placeholder='150,00')
    fornecedor=discord.ui.TextInput(label='Fornecedor / marketplace',placeholder='BUFF / CSFloat / vendedor')
    floatv=discord.ui.TextInput(label='Float encontrado',placeholder='0.215',required=False)
    links=discord.ui.TextInput(label='Listing / Inspect',placeholder='Cole o link do anúncio e/ou inspect',required=False,style=discord.TextStyle.paragraph)
    def __init__(self,code):super().__init__();self.code=code
    async def on_submit(self,i):
        await i.response.defer(ephemeral=True)
        try:cost=D(self.custo.value);price=D(self.preco.value)
        except:return await i.followup.send('❌ Custo ou preço inválido.',ephemeral=True)
        if cost<=0 or price<=0:return await i.followup.send('❌ Custo e preço precisam ser maiores que zero.',ephemeral=True)
        if self.floatv.value and not valid_float(self.floatv.value):return await i.followup.send('❌ Float encontrado inválido.',ephemeral=True)
        raw=self.links.value.strip();listing=raw if raw.startswith('http') else None;inspect=raw if raw and not raw.startswith('http') else None
        with Session.begin() as s:
            o=s.scalar(select(Order).where(Order.guild_id==gid(i),Order.code==self.code).with_for_update())
            if not o:return await i.followup.send('❌ Encomenda não encontrada.',ephemeral=True)
            if o.status!='SEARCHING':return await i.followup.send(f'❌ A encomenda está em {order_status_label(o.status)}.',ephemeral=True)
            o.found_price=cost;o.customer_price=price;o.supplier=self.fornecedor.value[:80];o.found_float=self.floatv.value.replace(',','.') or None;o.listing_url=listing;o.inspect_link=inspect;o.status='FOUND';log(s,gid(i),i.user.id,'ORDER_FOUND_DETAILS','order',o.id,f'cost={cost}; price={price}; supplier={o.supplier}');oid=o.id
        with Session() as s:o=s.get(Order,oid)
        await sync_order_operation(o);await notify_order_customer(o)
        profit=price-cost;roi=(profit/cost*100) if cost else D(0)
        await i.followup.send(f'🎯 **{o.code}** registrada como SKIN ENCONTRADA.\nCusto: **{money(cost)}** • Cliente: **{money(price)}** • Lucro bruto: **{money(profit)}** • ROI: **{roi:.1f}%**\nRevise o card e clique **ENVIAR PROPOSTA**.',ephemeral=True)

class SendProposalModal(discord.ui.Modal,title='Enviar proposta ao cliente'):
    validade=discord.ui.TextInput(label='Validade em horas',default='24',placeholder='24')
    def __init__(self,code):super().__init__();self.code=code
    async def on_submit(self,i):
        await i.response.defer(ephemeral=True)
        try:hours=max(1,min(168,int(self.validade.value)))
        except:return await i.followup.send('❌ Informe a validade em horas (1 a 168).',ephemeral=True)
        with Session.begin() as s:
            o=s.scalar(select(Order).where(Order.guild_id==gid(i),Order.code==self.code).with_for_update())
            if not o:return await i.followup.send('❌ Encomenda não encontrada.',ephemeral=True)
            if o.status!='FOUND':return await i.followup.send('❌ A encomenda precisa estar em SKIN ENCONTRADA.',ephemeral=True)
            if o.found_price is None or o.customer_price is None or not o.supplier:return await i.followup.send('❌ Faltam custo, preço ao cliente ou fornecedor.',ephemeral=True)
            o.proposal_expires_at=datetime.now(timezone.utc)+timedelta(hours=hours);o.status='PROPOSAL_SENT';log(s,gid(i),i.user.id,'ORDER_PROPOSAL_SENT','order',o.id,f'{o.customer_price}; {hours}h');oid=o.id
        with Session() as s:o=s.get(Order,oid)
        try:profit,roi=await send_order_proposal(o)
        except Exception as e:
            with Session.begin() as s:x=s.get(Order,oid);x.status='FOUND'
            return await i.followup.send(f'❌ Não consegui enviar a proposta ao cliente: {e}',ephemeral=True)
        await sync_order_operation(o);await i.followup.send(f'💰 Proposta de **{money(o.customer_price)}** enviada ao cliente. Agora somente ele pode aceitar ou recusar. ROI bruto: **{roi:.1f}%**.',ephemeral=True)

class CancelOrderModal(discord.ui.Modal,title='Cancelar encomenda'):
    code=discord.ui.TextInput(label='Código da encomenda',placeholder='ENC-00001')
    async def on_submit(self,i):
        with Session.begin() as s:
            o=s.scalar(select(Order).where(Order.guild_id==gid(i),Order.code==self.code.value.upper(),Order.user_id==i.user.id).with_for_update())
            if not o:return await i.response.send_message('❌ Encomenda não encontrada.',ephemeral=True)
            if o.status not in ('OPEN','SEARCHING','FOUND','PROPOSAL_SENT'):return await i.response.send_message('❌ Esta encomenda já avançou demais para cancelamento automático. Fale com a equipe.',ephemeral=True)
            o.status='CANCELLED';log(s,gid(i),i.user.id,'ORDER_CANCEL','order',o.id,o.code)
        await sync_order_operation(o);await i.response.send_message(f'❌ **{o.code}** cancelada.',ephemeral=True)
class OrderCustomerView(discord.ui.View):
    def __init__(self):super().__init__(timeout=None)
    @discord.ui.button(label='CANCELAR ENCOMENDA',emoji='✖️',style=discord.ButtonStyle.danger,custom_id='v33:order:cancel')
    async def cancel(self,i,b):await i.response.send_modal(CancelOrderModal())

class FeedbackModal(discord.ui.Modal,title='Avaliar negociação verificada'):
    rating=discord.ui.TextInput(label='Nota de 1 a 5',placeholder='5')
    comment=discord.ui.TextInput(label='Comentário',required=False,style=discord.TextStyle.paragraph)
    def __init__(self,sale_code:str):
        super().__init__();self.sale_code=sale_code.upper()
    async def on_submit(self,i):
        try:r=int(self.rating.value)
        except:r=0
        if r<1 or r>5:return await i.response.send_message('❌ Use uma nota de 1 a 5.',ephemeral=True)
        with Session.begin() as s:
            sale=s.scalar(select(Sale).where(Sale.guild_id==gid(i),Sale.code==self.sale_code,Sale.buyer_id==i.user.id))
            if not sale or sale.status!='COMPLETED':return await i.response.send_message('❌ Essa venda não existe, não pertence a você ou ainda não foi concluída.',ephemeral=True)
            old=s.scalar(select(Feedback).where(Feedback.sale_id==sale.id))
            if old:return await i.response.send_message('⭐ Essa negociação já foi avaliada.',ephemeral=True)
            fb=Feedback(guild_id=gid(i),user_id=i.user.id,sale_id=sale.id,rating=r,comment=self.comment.value or None);s.add(fb);s.flush();log(s,gid(i),i.user.id,'FEEDBACK_CREATE','sale',sale.id,f'{r}/5')
        ch=channel(gid(i),'feedback')
        if isinstance(ch,discord.TextChannel):
            stars='⭐'*r
            e=discord.Embed(title=f'{stars} • NEGOCIAÇÃO VERIFICADA',description=self.comment.value or 'Sem comentário.',color=0xFEE75C)
            e.add_field(name='Negociação',value=self.sale_code);e.add_field(name='Cliente',value=i.user.mention);e.set_footer(text='CLUTCH CLUB • avaliação vinculada a uma venda concluída')
            try:await ch.send(embed=e)
            except:pass
        await i.response.send_message('⭐ Obrigado! Sua avaliação verificada foi registrada.',ephemeral=True)

class VerifiedFeedbackView(discord.ui.View):
    def __init__(self,sale_code:str):super().__init__(timeout=604800);self.sale_code=sale_code.upper()
    @discord.ui.button(label='AVALIAR NEGOCIAÇÃO',emoji='⭐',style=discord.ButtonStyle.primary)
    async def go(self,i,b):await i.response.send_modal(FeedbackModal(self.sale_code))

class ProposalResponseView(discord.ui.View):
    def __init__(self):super().__init__(timeout=None)
    @discord.ui.button(label='ACEITAR PROPOSTA',emoji='✅',style=discord.ButtonStyle.success,custom_id='v21:buy:accept')
    async def accept(self,i,b):
        code=_code_from_interaction_message(i,'BL')
        if not code:return await i.response.send_message('❌ Não consegui identificar a Buylist desta proposta.',ephemeral=True)
        # Aceite não precisa de modal. Além de ser uma etapa binária, isto evita
        # rejeição 50035 do Discord em modais sem componentes válidos.
        with Session.begin() as s:
            bl=s.scalar(select(Buylist).where(Buylist.guild_id==gid(i),Buylist.code==code,Buylist.user_id==i.user.id).with_for_update())
            if not bl or bl.status!='PROPOSED':return await i.response.send_message('❌ Não há proposta ativa para essa Buylist.',ephemeral=True)
            if bl.proposal_expires_at and utc_aware(bl.proposal_expires_at) < datetime.now(timezone.utc):
                bl.status='EXPIRED';return await i.response.send_message('⌛ Essa proposta expirou.',ephemeral=True)
            bl.status='ACCEPTED';proposal=bl.proposal
            op=s.scalar(select(Operation).where(Operation.guild_id==gid(i),Operation.kind=='BUYLIST',Operation.ref_code==code).order_by(Operation.id.desc()).with_for_update())
            if op:op.status='ACTION_REQUIRED'
            log(s,gid(i),i.user.id,'BUYLIST_ACCEPT','buylist',bl.id,str(proposal))
        await refresh_buylist_operation(code,gid(i))
        await i.response.send_message(f'✅ Proposta de **{money(proposal)}** aceita. A equipe foi avisada para receber a skin.',ephemeral=True)
    @discord.ui.button(label='CONTRAPROPOR',emoji='🔄',style=discord.ButtonStyle.secondary,custom_id='v21:buy:counter')
    async def counter(self,i,b):
        code=_code_from_interaction_message(i,'BL')
        if not code:return await i.response.send_message('❌ Não consegui identificar a Buylist desta proposta.',ephemeral=True)
        await i.response.send_modal(CounterModal(code))

class TradeLockModal(discord.ui.Modal,title='Registrar Trade Lock'):
    trade_lock_ate=discord.ui.TextInput(label='Trade Lock até',placeholder='Ex.: 26/09/2026 14:30',required=True,max_length=16)
    def __init__(self,code:str):
        super().__init__();self.code=normalize_order_code(code)
    async def on_submit(self,i:discord.Interaction):
        try:
            existing=find_order_by_code(self.code,gid(i))
            if not existing:raise ValueError('Encomenda não encontrada.')
            if existing.status!='ACQUIRED':raise ValueError(f'A encomenda precisa estar em ADQUIRIDA. Estado atual: {order_status_label(existing.status)}.')
            parsed=parse_trade_lock(str(self.trade_lock_ate.value))
            if parsed<=datetime.now(timezone.utc):raise ValueError('A data/hora do Trade Lock precisa estar no futuro.')
            o=advance_order(existing.guild_id,i.user.id,self.code,'TRADE_LOCK')
            with Session.begin() as s:
                x=s.get(Order,o.id);x.trade_lock_until=parsed
            with Session() as s:o=s.get(Order,o.id)
            await sync_order_operation(o);await notify_order_customer(o)
            await i.response.send_message(f'🔒 **{o.code}** → TRADE LOCK até **{trade_lock_display(o.trade_lock_until)}**.',ephemeral=True)
        except Exception as e:
            await i.response.send_message(f'❌ {e}',ephemeral=True)

class TradeLockDecisionView(discord.ui.View):
    def __init__(self,code:str):
        super().__init__(timeout=180);self.code=normalize_order_code(code)
    @discord.ui.button(label='TEM TRADE LOCK',emoji='🔒',style=discord.ButtonStyle.secondary)
    async def with_lock(self,i:discord.Interaction,b):
        if not staff(i.user):return await i.response.send_message('Somente a equipe.',ephemeral=True)
        await i.response.send_modal(TradeLockModal(self.code))
    @discord.ui.button(label='SEM LOCK → READY',emoji='🟢',style=discord.ButtonStyle.success)
    async def no_lock(self,i:discord.Interaction,b):
        if not staff(i.user):return await i.response.send_message('Somente a equipe.',ephemeral=True)
        try:
            existing=find_order_by_code(self.code,gid(i))
            if not existing:raise ValueError('Encomenda não encontrada.')
            if existing.status!='ACQUIRED':raise ValueError(f'A encomenda precisa estar em ADQUIRIDA. Estado atual: {order_status_label(existing.status)}.')
            o=advance_order(existing.guild_id,i.user.id,self.code,'READY')
            with Session.begin() as s:
                x=s.get(Order,o.id);x.trade_lock_until=None
            with Session() as s:o=s.get(Order,o.id)
            await sync_order_operation(o);await notify_order_customer(o)
            await i.response.send_message(f'📦 **{o.code}** → PRONTA PARA ENTREGA.',ephemeral=True)
        except Exception as e:
            await i.response.send_message(f'❌ {e}',ephemeral=True)

class BuylistProposalModal(discord.ui.Modal,title='Enviar proposta Buylist'):
    valor=discord.ui.TextInput(label='Valor da proposta',placeholder='150,00')
    validade=discord.ui.TextInput(label='Validade em horas',placeholder='24',default='24',required=True)
    def __init__(self,code:str):
        super().__init__();self.code=code.upper()
    async def on_submit(self,i):
        try:
            v=D(self.valor.value); hours=max(1,int(self.validade.value))
        except:
            return await i.response.send_message('❌ Valor ou validade inválidos.',ephemeral=True)
        with Session.begin() as s:
            b=s.scalar(select(Buylist).where(Buylist.guild_id==gid(i),Buylist.code==self.code).with_for_update())
            if not b or b.status not in ('PENDING','COUNTERED'):
                return await i.response.send_message('❌ Buylist não encontrada ou fora de análise.',ephemeral=True)
            b.proposal=v;b.status='PROPOSED';b.proposal_expires_at=datetime.now(timezone.utc)+timedelta(hours=hours);uid=b.user_id
            op=s.scalar(select(Operation).where(Operation.guild_id==gid(i),Operation.kind=='BUYLIST',Operation.ref_code==b.code,Operation.status.in_(['OPEN','WAITING','ACTION_REQUIRED'])).with_for_update())
            if op: op.status='WAITING'
            log(s,gid(i),i.user.id,'BUYLIST_PROPOSE','buylist',b.id,str(v))
        try:
            u=bot.get_user(uid) or await bot.fetch_user(uid)
            await u.send(f'💰 **PROPOSTA CLUTCH CLUB — {self.code}**\nNossa oferta: **{money(v)}**\nValidade: **{hours}h**\nResponda pelos botões abaixo.',view=ProposalResponseView())
        except Exception:
            pass
        await refresh_buylist_operation(self.code,gid(i))
        await i.response.send_message(f'💰 **{self.code}** → PROPOSTA de **{money(v)}** enviada. Aguardando o cliente.',ephemeral=True)

async def refresh_buylist_operation(code:str,guild_id:int):
    with Session.begin() as s:
        op=s.scalar(select(Operation).where(Operation.guild_id==guild_id,Operation.kind=='BUYLIST',Operation.ref_code==code).order_by(Operation.id.desc()).with_for_update())
        b=s.scalar(select(Buylist).where(Buylist.guild_id==guild_id,Buylist.code==code))
        if not op or not b:return
        base=f'**Skin:** {b.skin_name}\n**Exterior:** {b.exterior}\n**Float:** {b.floatv}\n**Desejado:** {money(b.desired_price)}'
        if b.proposal is not None: base+=f'\n**Última proposta Clutch:** {money(b.proposal)}'
        if b.status=='COUNTERED' and b.counterproposal is not None: base+=f'\n**Contraproposta do cliente:** {money(b.counterproposal)}\n\n➡️ Responda pela **AÇÃO / PRÓXIMA ETAPA**.'
        elif b.status=='PROPOSED': base+='\n\n⏳ Aguardando resposta do cliente.'
        elif b.status=='ACCEPTED': base+='\n\n✅ **CLIENTE ACEITOU** — aguarde/registre o recebimento da skin.'
        elif b.status=='RECEIVED': base+='\n\n📥 Skin recebida — pagamento pendente.'
        elif b.status=='PAID': base+='\n\n💸 Pagamento registrado — pronta para entrada em estoque.'
        op.title=f'BUYLIST — {b.code}';op.detail=base
        if b.status in ('PROPOSED',):op.status='WAITING'
        elif b.status in ('COUNTERED','ACCEPTED','RECEIVED','PAID'):op.status='ACTION_REQUIRED'
        elif b.status in ('COMPLETED','REJECTED','EXPIRED'):op.status='DONE'
        oid=op.id;mid=op.staff_message_id;cid=op.staff_channel_id
    await ticket_notice(guild_id,code,f'📌 **{code} — {b.status}**')
    if b.status in ('COMPLETED','REJECTED','EXPIRED'):await close_negotiation_ticket(guild_id,code,'Buylist encerrada')
    if mid and cid:
        ch=bot.get_channel(cid)
        if ch:
            try:
                m=await ch.fetch_message(mid)
                with Session() as s:op=s.get(Operation,oid)
                await m.edit(embed=operation_embed(op),view=OperationsView() if op.status not in ('DONE','CANCELLED') else None)
            except Exception as e:print(f'[BUYLIST] Falha ao atualizar {code}: {type(e).__name__}: {e}')

async def refresh_sale_operation(code:str,guild_id:int):
    with Session.begin() as s:
        op=s.scalar(select(Operation).where(Operation.guild_id==guild_id,Operation.kind=='SALE',Operation.ref_code==code).order_by(Operation.id.desc()).with_for_update())
        sale=s.scalar(select(Sale).where(Sale.guild_id==guild_id,Sale.code==code))
        if not op or not sale:return
        skin=s.get(Skin,sale.skin_id)
        label={'RESERVED':'PAGAMENTO PENDENTE','PAYMENT_CONFIRMED':'PAGAMENTO CONFIRMADO','TRADE_SENT':'TRADE ENVIADA','COMPLETED':'CONCLUÍDA','CANCELLED':'CANCELADA'}.get(sale.status,sale.status)
        op.title=f'RESERVA / VENDA — {sale.code}'
        op.detail=f'**Skin:** {skin.code if skin else "—"} • {skin.name if skin else "—"}\n**Valor:** {money(sale.sale_price)}\n**Etapa:** {label}' + (f'\n**Reserva expira:** {reservation_display(sale.reserved_until)}' if sale.status=='RESERVED' else '')
        op.status='DONE' if sale.status=='COMPLETED' else ('CANCELLED' if sale.status=='CANCELLED' else 'ACTION_REQUIRED')
        oid=op.id;mid=op.staff_message_id;cid=op.staff_channel_id
    await ticket_notice(guild_id,code,f'📌 **{code} — {label}**')
    if sale.status in ('COMPLETED','CANCELLED'):await close_negotiation_ticket(guild_id,code,'Venda encerrada')
    if mid and cid:
        ch=bot.get_channel(cid)
        if ch:
            try:
                m=await ch.fetch_message(mid)
                with Session() as s:op=s.get(Operation,oid)
                await m.edit(embed=operation_embed(op),view=OperationsView() if op.status not in ('DONE','CANCELLED') else None)
            except Exception as e:print(f'[SALE] Falha ao atualizar {code}: {type(e).__name__}: {e}')

async def buylist_button_step(i,code,new_status):
    with Session.begin() as s:
        b=s.scalar(select(Buylist).where(Buylist.guild_id==gid(i),Buylist.code==code).with_for_update())
        if not b:raise ValueError('Buylist não encontrada.')
        allowed={'ACCEPTED':['RECEIVED'],'RECEIVED':['PAID']}
        if new_status not in allowed.get(b.status,[]):raise ValueError(f'Transição inválida: {b.status} → {new_status}.')
        b.status=new_status;log(s,gid(i),i.user.id,'BUYLIST_STATUS','buylist',b.id,new_status)
    await refresh_buylist_operation(code,gid(i))

class BuylistStockModal(discord.ui.Modal,title='Adicionar skin ao estoque'):
    preco=discord.ui.TextInput(label='Preço de venda',placeholder='150,00')
    taxas=discord.ui.TextInput(label='Taxas de aquisição',placeholder='0,00',default='0',required=False)
    def __init__(self,code):super().__init__();self.code=code
    async def on_submit(self,i):
        await i.response.defer(ephemeral=True)
        try:price=D(self.preco.value);fees=D(self.taxas.value or '0')
        except:return await i.followup.send('❌ Preço ou taxas inválidos.',ephemeral=True)
        if price<=0:return await i.followup.send('❌ O preço de venda precisa ser maior que zero.',ephemeral=True)
        with Session.begin() as s:
            b=s.scalar(select(Buylist).where(Buylist.guild_id==gid(i),Buylist.code==self.code).with_for_update())
            if not b:return await i.followup.send('❌ Buylist não encontrada.',ephemeral=True)
            if b.status!='PAID':return await i.followup.send(f'❌ A Buylist precisa estar em PAID. Estado atual: {b.status}.',ephemeral=True)
            x=Skin(code='PENDING',guild_id=gid(i),name=b.skin_name,exterior=b.exterior,floatv=b.floatv,pattern=b.pattern,stickers=b.stickers,status='AVAILABLE',cost=b.proposal or b.counterproposal or b.desired_price or 0,acquisition_fees=fees,price=price,source='BUYLIST',source_ref=b.code);s.add(x);s.flush();x.code=next_skin_code(s,gid(i));b.stock_skin_id=x.id;b.status='COMPLETED';s.add(Ledger(guild_id=gid(i),skin_id=x.id,kind='ACQUISITION',amount=-x.cost,note=b.code))
            if fees:s.add(Ledger(guild_id=gid(i),skin_id=x.id,kind='ACQUISITION_FEE',amount=-fees,note=b.code))
            log(s,gid(i),i.user.id,'BUYLIST_STOCK','buylist',b.id,x.code);sid=x.id
        with Session() as s:x=s.get(Skin,sid)
        ch=channel(gid(i),'catalog')
        if isinstance(ch,discord.TextChannel):
            m=await ch.send(embed=skin_embed(x),view=SkinPurchaseView())
            with Session.begin() as s:y=s.get(Skin,sid);y.channel_id=ch.id;y.message_id=m.id
        await post_news(x,'Nova entrada via Buylist');await refresh_buylist_operation(self.code,gid(i))
        await i.followup.send(f'📦 **{self.code} → CONCLUÍDA**. {x.code} adicionada ao estoque por **{money(price)}**.',ephemeral=True)

class BuylistActionView(discord.ui.View):
    def __init__(self,code,status):
        super().__init__(timeout=120);self.code=code
        if status=='ACCEPTED':
            b=discord.ui.Button(label='CONFIRMAR SKIN RECEBIDA',emoji='📥',style=discord.ButtonStyle.success)
            async def cb(i):
                try:await i.response.defer(ephemeral=True);await buylist_button_step(i,self.code,'RECEIVED');await i.followup.send(f'📥 **{self.code} → SKIN RECEBIDA**.',ephemeral=True)
                except Exception as e:await i.followup.send(f'❌ {e}',ephemeral=True)
            b.callback=cb;self.add_item(b)
        elif status=='RECEIVED':
            b=discord.ui.Button(label='CONFIRMAR PIX PAGO',emoji='💸',style=discord.ButtonStyle.success)
            async def cb(i):
                try:await i.response.defer(ephemeral=True);await buylist_button_step(i,self.code,'PAID');await i.followup.send(f'💸 **{self.code} → PAGAMENTO REGISTRADO**.',ephemeral=True)
                except Exception as e:await i.followup.send(f'❌ {e}',ephemeral=True)
            b.callback=cb;self.add_item(b)
        elif status=='PAID':
            b=discord.ui.Button(label='ADICIONAR AO ESTOQUE',emoji='📦',style=discord.ButtonStyle.success)
            async def cb(i):await i.response.send_modal(BuylistStockModal(self.code))
            b.callback=cb;self.add_item(b)

class SaleCompleteModal(discord.ui.Modal,title='Concluir venda'):
    taxas=discord.ui.TextInput(label='Taxas da venda',placeholder='0,00',default='0',required=False)
    def __init__(self,code):super().__init__();self.code=code
    async def on_submit(self,i):
        await i.response.defer(ephemeral=True)
        try:sale,x=sale_step(gid(i),i.user.id,self.code,'COMPLETED',self.taxas.value or '0')
        except Exception as e:return await i.followup.send(f'❌ {e}',ephemeral=True)
        await refresh_skin(x.id);await refresh_sale_operation(sale.code,gid(i));await post_sold(sale,x);await invite_feedback(sale)
        await i.followup.send(f'🎉 **{sale.code} → VENDA CONCLUÍDA**. Financeiro e estoque atualizados.',ephemeral=True)

class SaleActionView(discord.ui.View):
    def __init__(self,code,status):
        super().__init__(timeout=120);self.code=code
        labels={'RESERVED':('CONFIRMAR PAGAMENTO','💳','PAYMENT_CONFIRMED'),'PAYMENT_CONFIRMED':('CONFIRMAR TRADE ENVIADA','📦','TRADE_SENT')}
        if status in labels:
            label,emoji,target=labels[status];b=discord.ui.Button(label=label,emoji=emoji,style=discord.ButtonStyle.success)
            async def cb(i):
                await i.response.defer(ephemeral=True)
                try:sale,x=sale_step(gid(i),i.user.id,self.code,target);await refresh_skin(x.id);await refresh_sale_operation(sale.code,gid(i));await i.followup.send(f'✅ **{sale.code} → {sale.status}**.',ephemeral=True)
                except Exception as e:await i.followup.send(f'❌ {e}',ephemeral=True)
            b.callback=cb;self.add_item(b)
        elif status=='TRADE_SENT':
            b=discord.ui.Button(label='CONCLUIR VENDA',emoji='✅',style=discord.ButtonStyle.success)
            async def cb(i):await i.response.send_modal(SaleCompleteModal(self.code))
            b.callback=cb;self.add_item(b)

class OperationsView(discord.ui.View):
    def __init__(self):super().__init__(timeout=None)
    @discord.ui.button(label='ASSUMIR',emoji='👤',style=discord.ButtonStyle.primary,custom_id='v32:ops:claim')
    async def claim(self,i,b):
        if not staff(i.user):return await i.response.send_message('Somente a equipe.',ephemeral=True)
        await i.response.defer(ephemeral=True)
        op=await resolve_operation_by_message(i,'ACTION_REQUIRED');await i.followup.send(f'👤 {op.ref_code} assumida por {i.user.mention}.' if op else 'Pendência não encontrada.',ephemeral=True)
    @discord.ui.button(label='AÇÃO / PRÓXIMA ETAPA',emoji='➡️',style=discord.ButtonStyle.success,custom_id='v331:ops:next')
    async def done(self,i,b):
        if not staff(i.user):return await i.response.send_message('Somente a equipe.',ephemeral=True)
        with Session() as s: op=s.scalar(select(Operation).where(Operation.guild_id==gid(i),Operation.staff_message_id==i.message.id))
        if not op:return await i.response.send_message('Pendência não encontrada.',ephemeral=True)
        if op.kind=='BUYLIST':
            with Session() as s:bl=s.scalar(select(Buylist).where(Buylist.guild_id==gid(i),Buylist.code==op.ref_code))
            if not bl:return await i.response.send_message('❌ Buylist não encontrada.',ephemeral=True)
            if bl.status in ('PENDING','COUNTERED'):
                return await i.response.send_modal(BuylistProposalModal(bl.code))
            if bl.status=='PROPOSED':
                return await i.response.send_message('⏳ Aguardando o **cliente** aceitar ou contrapropor. A Buylist não será encerrada.',ephemeral=True)
            if bl.status in ('ACCEPTED','RECEIVED','PAID'):
                text={'ACCEPTED':'✅ Cliente aceitou. Confirme quando a skin chegar.','RECEIVED':'📥 Skin recebida. Confirme o pagamento ao cliente.','PAID':'💸 Pagamento registrado. Cadastre a skin no estoque.'}[bl.status]
                return await i.response.send_message(text,view=BuylistActionView(bl.code,bl.status),ephemeral=True)
            if bl.status in ('COMPLETED','REJECTED','EXPIRED'):
                await i.response.defer(ephemeral=True);op=await resolve_operation_by_message(i,'DONE');return await i.followup.send(f'✅ {op.ref_code} encerrada ({bl.status}).' if op else 'Pendência não encontrada.',ephemeral=True)
            return await i.response.send_message(f'ℹ️ Estado atual da Buylist: **{bl.status}**.',ephemeral=True)
        if op.kind=='SALE':
            with Session() as s:
                sale=s.scalar(select(Sale).where(Sale.guild_id==gid(i),Sale.code==op.ref_code))
                skin=s.get(Skin,sale.skin_id) if sale else None
            if not sale:return await i.response.send_message('❌ Venda/reserva não encontrada.',ephemeral=True)
            if sale.status in ('RESERVED','PAYMENT_CONFIRMED','TRADE_SENT'):
                text={'RESERVED':f'💳 **{sale.code} — PAGAMENTO PENDENTE**\nValor: **{money(sale.sale_price)}**. Confirme somente após conferir o recebimento.','PAYMENT_CONFIRMED':f'✅ **{sale.code} — PAGAMENTO CONFIRMADO**\nEnvie a Trade Offer e confirme pelo botão abaixo.','TRADE_SENT':f'📦 **{sale.code} — TRADE ENVIADA**\nQuando a entrega estiver confirmada, conclua a venda pelo botão abaixo.'}[sale.status]
                return await i.response.send_message(text,view=SaleActionView(sale.code,sale.status),ephemeral=True)
            if sale.status=='COMPLETED':
                await i.response.defer(ephemeral=True);doneop=await resolve_operation_by_message(i,'DONE');return await i.followup.send(f'🎉 **{sale.code}** já está concluída.',ephemeral=True)
            if sale.status=='CANCELLED':
                await i.response.defer(ephemeral=True);doneop=await resolve_operation_by_message(i,'CANCELLED');return await i.followup.send(f'❌ **{sale.code}** está cancelada.',ephemeral=True)
            return await i.response.send_message(f'ℹ️ Estado atual da venda: **{sale.status}**.',ephemeral=True)
        if op.kind!='ORDER':
            return await i.response.send_message(f'ℹ️ A operação **{op.ref_code}** não possui avanço automático neste botão.',ephemeral=True)
        with Session() as s:o=s.scalar(select(Order).where(Order.guild_id==gid(i),Order.code==op.ref_code))
        if not o:return await i.response.send_message('❌ Encomenda não encontrada.',ephemeral=True)
        if o.status=='OPEN':
            await i.response.defer(ephemeral=True);o=advance_order(gid(i),i.user.id,o.code,'SEARCHING');await sync_order_operation(o);await notify_order_customer(o);return await i.followup.send(f'🔎 **{o.code}** → PROCURANDO.',ephemeral=True)
        if o.status=='SEARCHING':return await i.response.send_modal(FoundSkinModal(o.code))
        if o.status=='FOUND':return await i.response.send_modal(SendProposalModal(o.code))
        if o.status=='PROPOSAL_SENT':return await i.response.send_message('⏳ Aguardando o **cliente** aceitar ou recusar a proposta. O Staff não pode avançar esta etapa.',ephemeral=True)
        if o.status=='CUSTOMER_ACCEPTED':
            return await i.response.send_message('⏳ O cliente aceitou e precisa escolher **PIX** ou **CARTÃO** na mensagem privada. Não avance manualmente.',ephemeral=True)
        if o.status=='PAYMENT_PENDING':
            method=cfg(o.guild_id,f'order_payment_method_{o.id}','PIX')
            text=(f'💳 **{o.code} — PAGAMENTO PENDENTE**\nMétodo: **{method}**\nConfirme somente depois de conferir o recebimento.' if method=='PIX' else f'💳 **{o.code} — PAGAMENTO PENDENTE**\nMétodo: **CARTÃO**\nEnvie o link ao cliente e confirme somente depois de conferir o recebimento.')
            return await i.response.send_message(text,view=OrderPaymentStaffView(o.code,method),ephemeral=True)
        if o.status=='PAYMENT_CONFIRMED':
            await i.response.defer(ephemeral=True);o=advance_order(gid(i),i.user.id,o.code,'AWAITING_ACQUISITION');await sync_order_operation(o);await notify_order_customer(o);return await i.followup.send(f'🛒 **{o.code}** → AGUARDANDO AQUISIÇÃO.',ephemeral=True)
        if o.status=='AWAITING_ACQUISITION':
            await i.response.defer(ephemeral=True);o=advance_order(gid(i),i.user.id,o.code,'ACQUIRED');await sync_order_operation(o);await notify_order_customer(o);return await i.followup.send(f'✅ **{o.code}** → ADQUIRIDA.',ephemeral=True)
        if o.status=='ACQUIRED':return await i.response.send_message('A skin possui **Trade Lock**?',view=TradeLockDecisionView(o.code),ephemeral=True)
        if o.status=='TRADE_LOCK':
            if o.trade_lock_until and utc_aware(o.trade_lock_until)>datetime.now(timezone.utc):return await i.response.send_message(f'🔒 Trade Lock ativo até **{trade_lock_display(o.trade_lock_until)}**.',ephemeral=True)
            await i.response.defer(ephemeral=True);o=advance_order(gid(i),i.user.id,o.code,'READY');await sync_order_operation(o);await notify_order_customer(o);return await i.followup.send(f'📦 **{o.code}** → PRONTA PARA ENTREGA.',ephemeral=True)
        if o.status=='READY':
            await i.response.defer(ephemeral=True)
            # Finance first, status second: if the ledger cannot close, the order
            # remains READY instead of becoming delivered with missing revenue.
            finalize_order_financials(gid(i),i.user.id,o)
            o=advance_order(gid(i),i.user.id,o.code,'DELIVERED')
            await sync_order_operation(o);await notify_order_customer(o)
            return await i.followup.send(f'🎉 **{o.code}** → ENTREGUE. Financeiro registrado.',ephemeral=True)
        return await i.response.send_message(f'ℹ️ Estado atual: **{order_status_label(o.status)}**.',ephemeral=True)
    @discord.ui.button(label='CANCELAR',emoji='✖️',style=discord.ButtonStyle.danger,custom_id='v32:ops:cancel')
    async def cancel(self,i,b):
        if not staff(i.user):return await i.response.send_message('Somente a equipe.',ephemeral=True)
        await i.response.defer(ephemeral=True)
        with Session.begin() as s:
            op=s.scalar(select(Operation).where(Operation.guild_id==gid(i),Operation.staff_message_id==i.message.id).with_for_update())
            if not op:return await i.followup.send('Pendência não encontrada.',ephemeral=True)
            if op.kind=='ORDER':
                o=s.scalar(select(Order).where(Order.guild_id==gid(i),Order.code==op.ref_code).with_for_update())
                if o and o.status not in ('DELIVERED','CANCELLED'):o.status='CANCELLED';log(s,gid(i),i.user.id,'ORDER_CANCEL_STAFF','order',o.id,o.code)
            op.status='CANCELLED';oid=op.id
        with Session() as s:op=s.get(Operation,oid)
        try:await i.message.edit(embed=operation_embed(op),view=None)
        except:pass
        await i.followup.send(f'✖️ {op.ref_code} encerrada.',ephemeral=True)

class ClubQuickAccessView(discord.ui.View):
    """V3.8.3: direct channel shortcuts; independent from Discord Community Onboarding."""
    def __init__(self, guild_id:int):
        super().__init__(timeout=300)
        specs=[
            ('🟢 CATÁLOGO','catalog'),
            ('📦 ENCOMENDAR','order'),
            ('🔔 INTERESSE','interest'),
            ('⭐ AVALIAÇÕES','feedback'),
        ]
        for label,key in specs:
            ch=channel(guild_id,key)
            if isinstance(ch,discord.TextChannel):
                self.add_item(discord.ui.Button(label=label,style=discord.ButtonStyle.link,url=f'https://discord.com/channels/{guild_id}/{ch.id}'))

class OnboardingView(discord.ui.View):
    def __init__(self):super().__init__(timeout=None)
    @discord.ui.button(label='ENTRAR PARA O CLUB',emoji='👑',style=discord.ButtonStyle.success,custom_id='v367:onboarding:join')
    async def join_club(self,i:discord.Interaction,b):
        if not i.guild or not isinstance(i.user,discord.Member):
            return await i.response.send_message('❌ Use este botão dentro do servidor da Clutch Club.',ephemeral=True)
        role_id=cfg(i.guild.id,'customer_role_id')
        if not role_id:
            return await i.response.send_message('❌ O cargo de cliente ainda não foi configurado pela equipe.',ephemeral=True)
        role=i.guild.get_role(int(role_id))
        if not role:
            return await i.response.send_message('❌ O cargo configurado não existe mais. Avise a equipe.',ephemeral=True)
        me=i.guild.me
        if not me or not me.guild_permissions.manage_roles or role>=me.top_role:
            return await i.response.send_message('❌ Não consigo liberar seu acesso: o cargo do Clutch Bot precisa ficar acima do cargo de Cliente e ter **Gerenciar Cargos**.',ephemeral=True)
        try:
            # V3.8.1: o botão é a autoridade do acesso. Mesmo quem já possui
            # o cargo Cliente passa pela verificação/reparo da matriz de canais.
            already_member = role in i.user.roles
            if not already_member:
                await i.user.add_roles(role,reason='Clutch Club onboarding concluído')

            access_ok, access_details = await repair_customer_access(i.guild.id)

            with Session.begin() as s:
                detail=f'role={role.id}; already_member={already_member}; access_ok={access_ok}'
                log(s,i.guild.id,i.user.id,'ONBOARDING_COMPLETE','member',None,detail)

            # Entrega atalhos diretos para os canais críticos. Isso evita depender
            # da lista personalizada do Onboarding do Discord para o usuário chegar à Loja.
            links=[]
            for key in ('catalog','interest','order','feedback'):
                ch=channel(i.guild.id,key)
                if isinstance(ch,discord.TextChannel):
                    links.append(ch.mention)
            channels_text=' • '.join(links)

            if access_ok:
                msg='👑 **Bem-vindo ao Club!** Seu cargo **Cliente** e o acesso aos canais da Loja e da Comunidade foram verificados.'
                if channels_text:
                    msg += f'\n\n🛒 **Acessos rápidos:** {channels_text}'
                if already_member:
                    msg += '\n\n🔄 Você já era Cliente; o Clutch OS reconferiu seu acesso.'
                await i.response.send_message(msg,view=ClubQuickAccessView(i.guild.id),ephemeral=True)
            else:
                print(f'[ONBOARDING ACCESS] falha para {i.user} ({i.user.id}): {access_details}')
                await i.response.send_message('⚠️ Seu cargo **Cliente** foi aplicado, mas o Clutch OS encontrou uma divergência ao validar os canais. A equipe foi informada para corrigir o acesso.',ephemeral=True)
        except discord.Forbidden:
            await i.response.send_message('❌ O Discord bloqueou a atribuição do cargo/acesso. Confira a hierarquia e as permissões do Clutch Bot.',ephemeral=True)
        except discord.HTTPException as exc:
            print(f'[ONBOARDING ACCESS] HTTP error para {i.user} ({i.user.id}): {exc}')
            await i.response.send_message('❌ O Discord recusou a atualização do acesso neste momento. Tente novamente em alguns segundos.',ephemeral=True)

def onboarding_embed():
    e=discord.Embed(title='👑 BEM-VINDO À CLUTCH CLUB',description='Sua central para **comprar, vender e encomendar skins de CS2**.\n\n📜 Confira **Como Funciona**\n🛡️ Leia nossas orientações de **Segurança**\n🤝 Negocie somente pelos canais oficiais\n\nClique em **ENTRAR PARA O CLUB**. O Clutch Bot libera/verifica seu cargo **💎 Cliente** e entrega atalhos diretos para a Loja — sem depender do Community Onboarding do Discord.',color=0xF1C40F)
    e.set_footer(text='CLUTCH CLUB • PLAY • TRADE • JOIN THE CLUB.')
    return e

async def ensure_onboarding_panel(g):
    ch_id=cfg(g,'welcome_channel_id')
    ch=bot.get_channel(int(ch_id)) if ch_id else None
    if not isinstance(ch,discord.TextChannel):
        print('[ONBOARDING] canal não configurado/encontrado')
        return False
    try:
        with Session() as s:p=s.get(Panel,(g,'onboarding'))
        msg=None
        if p and p.channel_id==ch.id:
            try:msg=await ch.fetch_message(p.message_id)
            except:msg=None
        if msg:await msg.edit(embed=onboarding_embed(),view=OnboardingView())
        else:
            msg=await ch.send(embed=onboarding_embed(),view=OnboardingView())
            with Session.begin() as s:s.merge(Panel(guild_id=g,panel_key='onboarding',channel_id=ch.id,message_id=msg.id))
        print(f'[ONBOARDING] #{ch.name} ({ch.id}) OK')
        return True
    except Exception as e:
        print(f'[ONBOARDING] erro: {type(e).__name__}: {e}')
        return False

def public_base_url():
    raw=(os.getenv('PUBLIC_BASE_URL') or '').strip().rstrip('/')
    if raw:
        return raw
    domain=(os.getenv('RAILWAY_PUBLIC_DOMAIN') or '').strip().strip('/')
    return f'https://{domain}' if domain else ''

class SkinEditDataModal(discord.ui.Modal,title='Editar skin • Dados'):
    def __init__(self,skin):
        super().__init__(); self.skin_id=skin.id
        self.name=discord.ui.TextInput(label='Nome',default=skin.name,max_length=180)
        self.exterior=discord.ui.TextInput(label='Exterior',default=skin.exterior or '',required=False,max_length=40)
        self.floatv=discord.ui.TextInput(label='Float',default=skin.floatv or '',required=False,max_length=32)
        self.pattern=discord.ui.TextInput(label='Pattern',default=skin.pattern or '',required=False,max_length=32)
        self.stickers=discord.ui.TextInput(label='Stickers / observações',default=skin.stickers or '',required=False,style=discord.TextStyle.paragraph,max_length=1000)
        for x in (self.name,self.exterior,self.floatv,self.pattern,self.stickers): self.add_item(x)
    async def on_submit(self,i):
        if not staff(i.user): return await i.response.send_message('❌ Apenas Staff/Fundador pode editar skins.',ephemeral=True)
        if self.floatv.value and not valid_float(self.floatv.value): return await i.response.send_message('❌ Float inválido. Use 0 a 1.',ephemeral=True)
        await i.response.defer(ephemeral=True)
        with Session.begin() as s:
            x=s.get(Skin,self.skin_id)
            if not x:return await i.followup.send('❌ Skin não encontrada.',ephemeral=True)
            if x.status=='RESERVED':return await i.followup.send('🔒 A skin está reservada. Cancele/finalize a negociação antes de alterar dados críticos.',ephemeral=True)
            before=f'{x.name}|{x.exterior}|{x.floatv}|{x.pattern}'
            x.name=self.name.value.strip();x.exterior=self.exterior.value.strip().upper() or None;x.floatv=self.floatv.value.strip().replace(',','.') or None;x.pattern=self.pattern.value.strip() or None;x.stickers=self.stickers.value.strip() or None
            log(s,gid(i),i.user.id,'SKIN_EDIT_DATA','skin',x.id,before)
        await refresh_skin(self.skin_id)
        await i.followup.send('✅ Dados da skin atualizados no mesmo anúncio.',ephemeral=True)

class SkinEditValuesModal(discord.ui.Modal,title='Editar skin • Valores'):
    def __init__(self,skin):
        super().__init__();self.skin_id=skin.id
        self.price=discord.ui.TextInput(label='Preço de venda',default=str(skin.price or 0),max_length=24)
        self.cost=discord.ui.TextInput(label='Custo',default=str(skin.cost or 0),max_length=24)
        self.fees=discord.ui.TextInput(label='Taxas de aquisição',default=str(skin.acquisition_fees or 0),max_length=24)
        for x in (self.price,self.cost,self.fees):self.add_item(x)
    async def on_submit(self,i):
        if not staff(i.user):return await i.response.send_message('❌ Apenas Staff/Fundador pode editar skins.',ephemeral=True)
        try: price,cost,fees=D(self.price.value),D(self.cost.value),D(self.fees.value)
        except:return await i.response.send_message('❌ Valor inválido.',ephemeral=True)
        await i.response.defer(ephemeral=True)
        with Session.begin() as s:
            x=s.get(Skin,self.skin_id)
            if not x:return await i.followup.send('❌ Skin não encontrada.',ephemeral=True)
            if x.status=='RESERVED':return await i.followup.send('🔒 A skin está reservada. Não altere preço/custo durante uma negociação.',ephemeral=True)
            before=f'price={x.price};cost={x.cost};fees={x.acquisition_fees}'
            x.price=price;x.cost=cost;x.acquisition_fees=fees;log(s,gid(i),i.user.id,'SKIN_EDIT_VALUES','skin',x.id,before)
        await refresh_skin(self.skin_id)
        await i.followup.send('✅ Valores atualizados no mesmo anúncio.',ephemeral=True)

class SkinEditMediaModal(discord.ui.Modal,title='Editar skin • Mídia e Inspect'):
    def __init__(self,skin):
        super().__init__();self.skin_id=skin.id
        self.inspect=discord.ui.TextInput(label='Inspect link',default=skin.inspect or '',required=False,style=discord.TextStyle.paragraph,max_length=1000)
        self.image=discord.ui.TextInput(label='URL da imagem',default=skin.image_url or '',required=False,style=discord.TextStyle.paragraph,max_length=1000)
        self.add_item(self.inspect);self.add_item(self.image)
    async def on_submit(self,i):
        if not staff(i.user):return await i.response.send_message('❌ Apenas Staff/Fundador pode editar skins.',ephemeral=True)
        inspect=self.inspect.value.strip() or None; image=self.image.value.strip() or None
        if inspect and not inspect.startswith('steam://run/730//+csgo_econ_action_preview'):
            return await i.response.send_message('❌ Inspect inválido. Use o link steam://run/730//+csgo_econ_action_preview...',ephemeral=True)
        if image and not image.startswith(('http://','https://')):
            return await i.response.send_message('❌ A imagem precisa ser uma URL http/https.',ephemeral=True)
        await i.response.defer(ephemeral=True)
        with Session.begin() as s:
            x=s.get(Skin,self.skin_id)
            if not x:return await i.followup.send('❌ Skin não encontrada.',ephemeral=True)
            x.inspect=inspect;x.image_url=image;log(s,gid(i),i.user.id,'SKIN_EDIT_MEDIA','skin',x.id,'inspect/image')
        await refresh_skin(self.skin_id)
        await i.followup.send('✅ Imagem/Inspect atualizados no mesmo anúncio.',ephemeral=True)

class SkinEditMenuView(discord.ui.View):
    def __init__(self,skin_id:int):super().__init__(timeout=180);self.skin_id=skin_id
    def get_skin(self):
        with Session() as s:return s.get(Skin,self.skin_id)
    @discord.ui.button(label='DADOS',emoji='📝',style=discord.ButtonStyle.secondary)
    async def data(self,i,b):
        x=self.get_skin();
        if not x:return await i.response.send_message('❌ Skin não encontrada.',ephemeral=True)
        await i.response.send_modal(SkinEditDataModal(x))
    @discord.ui.button(label='VALORES',emoji='💰',style=discord.ButtonStyle.secondary)
    async def values(self,i,b):
        x=self.get_skin();
        if not x:return await i.response.send_message('❌ Skin não encontrada.',ephemeral=True)
        await i.response.send_modal(SkinEditValuesModal(x))
    @discord.ui.button(label='IMAGEM / INSPECT',emoji='🖼️',style=discord.ButtonStyle.secondary)
    async def media(self,i,b):
        x=self.get_skin();
        if not x:return await i.response.send_message('❌ Skin não encontrada.',ephemeral=True)
        await i.response.send_modal(SkinEditMediaModal(x))
    @discord.ui.button(label='EXCLUIR SKIN',emoji='🗑️',style=discord.ButtonStyle.danger)
    async def delete_skin(self,i,b):
        if not staff(i.user):return await i.response.send_message('❌ Apenas Staff/Fundador pode excluir skins.',ephemeral=True)
        x=self.get_skin()
        if not x:return await i.response.send_message('❌ Skin não encontrada.',ephemeral=True)
        if x.status in ('SOLD','PERSONAL','TEST_ARCHIVED','DELETED'):
            return await i.response.send_message(f'❌ {x.code} não pode ser excluída no status {x.status}.',ephemeral=True)
        await i.response.send_message(f'⚠️ **Excluir {x.code} • {x.name}?**\nO anúncio será removido e a skin sairá do estoque. Histórico financeiro/operações existentes será preservado.\n\nEsta ação exige confirmação.',view=SkinDeleteConfirmView(x.id),ephemeral=True)

class SkinDeleteConfirmView(discord.ui.View):
    def __init__(self,skin_id:int):super().__init__(timeout=90);self.skin_id=skin_id
    @discord.ui.button(label='CANCELAR',emoji='↩️',style=discord.ButtonStyle.secondary)
    async def cancel(self,i,b):
        await i.response.edit_message(content='↩️ Exclusão cancelada. Nenhuma alteração foi feita.',view=None)
    @discord.ui.button(label='CONFIRMAR EXCLUSÃO',emoji='🗑️',style=discord.ButtonStyle.danger)
    async def confirm(self,i,b):
        if not staff(i.user):return await i.response.send_message('❌ Apenas Staff/Fundador pode excluir skins.',ephemeral=True)
        await i.response.defer(ephemeral=True)
        old_code=None; channel_id=None; message_id=None; cancelled_sale=None
        with Session.begin() as s:
            x=s.get(Skin,self.skin_id)
            if not x:return await i.followup.send('❌ Skin não encontrada.',ephemeral=True)
            if x.status in ('SOLD','PERSONAL','TEST_ARCHIVED','DELETED'):
                return await i.followup.send(f'❌ {x.code} não pode ser excluída no status {x.status}.',ephemeral=True)
            sale=s.scalar(select(Sale).where(Sale.skin_id==x.id).order_by(Sale.id.desc()))
            if sale and sale.status in ('PAYMENT_CONFIRMED','TRADE_SENT','COMPLETED'):
                return await i.followup.send(f'🔒 Não é possível excluir {x.code}: {sale.code} está em {sale.status}. Finalize/cancele corretamente a negociação.',ephemeral=True)
            if sale and sale.status=='RESERVED':
                sale.status='CANCELLED'; cancelled_sale=sale.code
                log(s,x.guild_id,i.user.id,'SALE_STATUS','sale',sale.id,'RESERVED->CANCELLED; skin deleted by staff')
            old_code=x.code;channel_id=x.channel_id;message_id=x.message_id
            x.code=f'DEL-{x.id:05d}';x.status='DELETED';x.reserved_by=None;x.reserved_until=None;x.channel_id=None;x.message_id=None
            log(s,x.guild_id,i.user.id,'SKIN_DELETE','skin',x.id,f'{old_code}->DELETED; history preserved')
        if channel_id and message_id:
            ch=bot.get_channel(int(channel_id))
            if isinstance(ch,discord.TextChannel):
                try:
                    msg=await ch.fetch_message(int(message_id));await msg.delete()
                except discord.NotFound:pass
                except Exception as e:print(f'[SKIN DELETE] {old_code} anúncio: {type(e).__name__}: {e}')
        if cancelled_sale:
            await refresh_sale_operation(cancelled_sale,gid(i))
            await ticket_notice(gid(i),cancelled_sale,f'🗑️ **{old_code} removida do estoque pela equipe.** A reserva foi cancelada sem lançamento financeiro.')
            await close_negotiation_ticket(gid(i),cancelled_sale,'Reserva cancelada — skin removida do estoque')
        print(f'[SKIN DELETE] {old_code} -> DELETED | código público liberado para reutilização')
        await i.followup.send(f'✅ **{old_code} excluída do estoque e do catálogo.** O histórico foi preservado e o código público poderá ser reutilizado.',ephemeral=True)

class SkinPurchaseView(discord.ui.View):
    def __init__(self, skin=None):
        super().__init__(timeout=None)
        # RESERVED keeps Staff edit + inspect visible, but removes COMPRAR from the public card.
        if skin is not None and getattr(skin,'status',None) != 'AVAILABLE':
            for child in list(self.children):
                if getattr(child,'custom_id',None) == 'v370:skin:buy':
                    self.remove_item(child)
        # Discord link buttons require http/https. The public Clutch route then opens steam://.
        if skin is not None and getattr(skin,'inspect',None):
            base=public_base_url()
            if base:
                self.add_item(discord.ui.Button(label='INSPECIONAR NO CS2',emoji='🎮',style=discord.ButtonStyle.link,url=f'{base}/inspect/{skin.code}'))
    @discord.ui.button(label='EDITAR SKIN',emoji='✏️',style=discord.ButtonStyle.secondary,custom_id='v384:skin:edit')
    async def edit_skin(self,i,b):
        if not staff(i.user):return await i.response.send_message('❌ Apenas Staff/Fundador pode editar skins.',ephemeral=True)
        code=_code_from_interaction_message(i,'SK')
        if not code:return await i.response.send_message('❌ Não consegui identificar a skin deste anúncio.',ephemeral=True)
        with Session() as s:x=s.scalar(select(Skin).where(Skin.guild_id==gid(i),Skin.code==code))
        if not x:return await i.response.send_message('❌ Skin não encontrada.',ephemeral=True)
        await i.response.send_message(f'✏️ **Editar {x.code} • {x.name}**\nEscolha o grupo de dados que deseja alterar. O mesmo anúncio será atualizado.',view=SkinEditMenuView(x.id),ephemeral=True)

    @discord.ui.button(label='COMPRAR',emoji='🛒',style=discord.ButtonStyle.success,custom_id='v370:skin:buy')
    async def buy(self,i,b):
        code=_code_from_interaction_message(i,'SK')
        if not code:return await i.response.send_message('❌ Não consegui identificar a skin deste anúncio.',ephemeral=True)
        try:sale,x=reserve(gid(i),i.user.id,code,RESERVATION_MINUTES)
        except Exception as e:return await i.response.send_message(f'❌ {e}',ephemeral=True)
        await refresh_skin(x.id)
        expires=reservation_display(sale.reserved_until)
        opid=queue_operation(gid(i),'SALE',sale.code,sale.id,i.user.id,f'RESERVA / VENDA — {sale.code}',f'**Skin:** {x.code} • {x.name}\n**Valor:** {money(sale.sale_price)}\n**Reserva expira:** {expires}\n\n⏱️ Se o pagamento não for confirmado até esse horário, a reserva será cancelada automaticamente.','HIGH')
        await publish_operation(opid)
        await ensure_negotiation_ticket(gid(i),i.user.id,sale.code,'SALE',f'🛒 COMPRA — {sale.code}',f'**Skin:** {x.code} • {x.name}\n**Valor:** {money(sale.sale_price)}\n**Reserva válida até:** {expires}\n\n⏱️ Finalize o pagamento dentro desse prazo. Após a confirmação do pagamento pela equipe, a expiração automática é interrompida.')
        await i.response.send_message(f'🔒 **{x.code}** reservada até **{expires}**. Pedido **{sale.code}**, valor **{money(sale.sale_price)}**. Seu ticket privado foi aberto.',ephemeral=True)

class PublicPanel(discord.ui.View):
    def __init__(self):super().__init__(timeout=None)
    @discord.ui.button(label='QUERO VENDER UMA SKIN',emoji='💰',style=discord.ButtonStyle.success,custom_id='v2:buy:new')
    async def buy(self,i,b):
        if not buylist_enabled():
            return await i.response.send_message('⏸️ **Buylist temporariamente pausada.** No momento a Clutch Club não está comprando skins diretamente. Você ainda pode comprar, encomendar ou cadastrar interesse.',ephemeral=True)
        await i.response.send_modal(BuyModal())
class CatalogPanel(discord.ui.View):
    def __init__(self):super().__init__(timeout=None)
    @discord.ui.button(label='COMPRAR / RESERVAR',emoji='🛒',style=discord.ButtonStyle.success,custom_id='v2:catalog:reserve')
    async def reserve_btn(self,i,b):await i.response.send_modal(ReserveModal())
class InterestPanel(discord.ui.View):
    def __init__(self):super().__init__(timeout=None)
    @discord.ui.button(label='CADASTRAR PROCURA',emoji='🔔',style=discord.ButtonStyle.primary,custom_id='v2:interest:new')
    async def go(self,i,b):await i.response.send_modal(InterestModal())
class OrderPanel(discord.ui.View):
    def __init__(self):super().__init__(timeout=None)
    @discord.ui.button(label='QUERO ENCOMENDAR',emoji='📬',style=discord.ButtonStyle.primary,custom_id='v2:order:new')
    async def go(self,i,b):await i.response.send_modal(OrderModal())
def panel_embed(k):
    data={'buylist':(('⏸️ BUYLIST TEMPORARIAMENTE PAUSADA','No momento a Clutch Club não está comprando skins diretamente. O histórico permanece preservado e o serviço poderá ser reativado pela equipe.') if not buylist_enabled() else ('💰 VENDA SUA SKIN PARA A CLUTCH CLUB','Envie sua skin para análise e receba uma proposta da nossa equipe. Clique abaixo para começar — nenhum /comando é necessário.')),'catalog':('🛒 CATÁLOGO CLUTCH CLUB','Veja as skins disponíveis e use o código SK-XXXXX para comprar ou reservar.'),'interest':('🔔 LISTA DE INTERESSE','Procurando uma skin específica? Cadastre seu interesse e avisaremos quando houver um match.'),'order':('📦 ENCOMENDE SUA SKIN','Não encontrou o que procura? Abra uma encomenda informando skin, exterior, float e orçamento.')};t,d=data[k];return discord.Embed(title=t,description=d,color=0x2B2D31)
def _message_has_custom_id(msg, custom_id:str):
    """Return True when a Discord message contains a component with custom_id."""
    try:
        for row in getattr(msg,'components',[]) or []:
            for item in getattr(row,'children',[]) or []:
                if getattr(item,'custom_id',None)==custom_id:
                    return True
    except Exception:
        pass
    return False

async def cleanup_paused_buylist_legacy_panels(guild_id:int, canonical_message_id:int|None=None):
    """V3.8.4.3: remove obsolete public buylist panels while paused.

    Only bot-authored messages containing the old v2:buy:new button are touched.
    Business history, negotiations and database records are never deleted.
    """
    if buylist_enabled():
        return 0
    ch=channel(guild_id,'buylist')
    if not isinstance(ch,discord.TextChannel):
        return 0
    removed=0
    try:
        async for msg in ch.history(limit=100):
            if canonical_message_id and msg.id==canonical_message_id:
                continue
            if not bot.user or msg.author.id!=bot.user.id:
                continue
            if not _message_has_custom_id(msg,'v2:buy:new'):
                continue
            try:
                await msg.delete()
                removed+=1
            except discord.Forbidden:
                # If deletion is unavailable, at least neutralize the obsolete action.
                try:
                    await msg.edit(embed=panel_embed('buylist'),view=None)
                except Exception:
                    pass
            except discord.HTTPException:
                try:
                    await msg.edit(embed=panel_embed('buylist'),view=None)
                except Exception:
                    pass
    except Exception as e:
        print(f'[BUYLIST UI] aviso ao limpar painel legado: {type(e).__name__}: {e}')
    if removed:
        print(f'[BUYLIST UI] {removed} painel(is) legado(s) removido(s); painel pausado canônico preservado.')
    return removed

async def normalize_skin_codes_v3844(guild_id:int):
    """One-shot normalization of the seven confirmed real inventory SK codes.

    Keeps immutable DB primary keys and every FK relationship intact. Test/residual
    rows are archived under TEST-* codes, then the seven valid rows are compacted
    to SK-00001..SK-00007. Discord catalog messages keep their original message_id.
    """
    marker='v3844_skin_codes_normalized'
    if cfg(guild_id,marker)=='1':
        print('[SK NORMALIZATION] já concluída; nenhuma alteração necessária.')
        return True
    mapping={
        'SK-00002':'SK-00001','SK-00003':'SK-00002','SK-00004':'SK-00003',
        'SK-00005':'SK-00004','SK-00007':'SK-00005','SK-00008':'SK-00006',
        'SK-00009':'SK-00007',
    }
    residual={'SK-00001','SK-00006','SK-00010'}
    changed=[]
    try:
        with Session.begin() as s:
            rows=list(s.scalars(select(Skin).where(Skin.guild_id==guild_id)).all())
            by_code={x.code:x for x in rows}
            missing=[c for c in mapping if c not in by_code]
            if missing:
                print('[SK NORMALIZATION] ABORTADA: códigos válidos ausentes: '+', '.join(missing))
                return False
            # Free destination codes without deleting historical/test rows.
            for old in residual:
                x=by_code.get(old)
                if x:
                    x.code=f'TEST-{old}'
                    x.status='TEST_ARCHIVED'
                    x.reserved_by=None; x.reserved_until=None
            # Temporary names avoid UNIQUE collisions while shifting the sequence.
            for old in mapping:
                x=by_code[old]; x.code=f'TMP-{x.id}'
            s.flush()
            for old,new in mapping.items():
                x=by_code[old]; x.code=new; changed.append((x.id,old,new,x.channel_id,x.message_id))
            s.merge(GuildConfig(guild_id=guild_id,key=marker,value='1'))
            s.add(Audit(guild_id=guild_id,actor_id=0,action='SK_NORMALIZATION_V3844',entity_type='skin',entity_id=None,detail='; '.join(f'{a}->{b}' for _,a,b,_,_ in changed)+'; NEXT=SK-00008'))
        print('[SK NORMALIZATION] banco OK | '+ ' | '.join(f'{a}->{b}' for _,a,b,_,_ in changed) +' | próximo=SK-00008')
    except Exception as e:
        print(f'[SK NORMALIZATION] FALHA; transação revertida: {type(e).__name__}: {e}')
        return False
    # Refresh only the seven affected catalog messages; never mass-patch the catalog.
    patched=missing_msg=failed=0
    for skin_id,old,new,chid,mid in changed:
        if not chid or not mid: continue
        ch=bot.get_channel(int(chid))
        if not isinstance(ch,discord.TextChannel): failed+=1; continue
        try:
            with Session() as s: x=s.get(Skin,skin_id)
            msg=await ch.fetch_message(int(mid))
            await msg.edit(embed=skin_embed(x),view=SkinPurchaseView(x) if x.status=='AVAILABLE' else None)
            patched+=1
            await asyncio.sleep(1.0)
        except discord.NotFound:
            missing_msg+=1
            print(f'[SK NORMALIZATION] {new}: anúncio antigo não existe; DB normalizado e message_id preservado para diagnóstico.')
        except Exception as e:
            failed+=1
            print(f'[SK NORMALIZATION] {new}: falha ao atualizar anúncio: {type(e).__name__}: {e}')
    print(f'[SK NORMALIZATION] Discord patched={patched} | mensagens_ausentes={missing_msg} | falhas={failed}')
    return True

async def migrate_legacy_skin_edit_buttons(guild_id:int):
    """V3.8.4.3 one-shot migration for catalog ads created before EDITAR SKIN.

    Patches only AVAILABLE catalog messages missing v384:skin:edit, preserving the
    same SK id, Discord message, image/embed data and all financial/history data.
    A DB marker prevents mass PATCH on future boots after a fully successful pass.
    """
    marker='v3843_legacy_skin_edit_migrated'
    if cfg(guild_id,marker)=='1':
        print('[CATALOG MIGRATION] anúncios legados já migrados; nenhum PATCH necessário.')
        return True
    with Session() as s:
        skins=list(s.scalars(select(Skin).where(Skin.guild_id==guild_id,Skin.status=='AVAILABLE')).all())
    candidates=[x for x in skins if x.channel_id and x.message_id]
    checked=patched=already=failed=0
    for x in candidates:
        ch=bot.get_channel(int(x.channel_id))
        if not isinstance(ch,discord.TextChannel):
            failed+=1; continue
        try:
            msg=await ch.fetch_message(int(x.message_id)); checked+=1
            if _message_has_custom_id(msg,'v384:skin:edit'):
                already+=1; continue
            await msg.edit(embed=skin_embed(x),view=SkinPurchaseView(x))
            patched+=1
        except (discord.NotFound,discord.Forbidden,discord.HTTPException) as e:
            failed+=1
            print(f'[CATALOG MIGRATION] {x.code} não migrada: {type(e).__name__}: {e}')
        except Exception as e:
            failed+=1
            print(f'[CATALOG MIGRATION] {x.code} erro inesperado: {type(e).__name__}: {e}')
    if failed==0:
        set_cfg(guild_id,marker,'1')
    print(f'[CATALOG MIGRATION] checked={checked} | patched={patched} | já_ok={already} | falhas={failed} | '+('concluída' if failed==0 else 'será retomada no próximo boot'))
    return failed==0

async def ensure_panel(g,key,view):
    """Create/update a public panel without allowing one bad channel to break startup."""
    ch=channel(g,key)
    if not isinstance(ch,discord.TextChannel):
        print(f'[PAINEL] {key:<8} NÃO CONFIGURADO ou canal não encontrado')
        return False, 'canal não configurado/encontrado'

    me=ch.guild.me
    perms=ch.permissions_for(me) if me else None
    required=('view_channel','send_messages','embed_links','read_message_history')
    missing=[name for name in required if not perms or not getattr(perms,name,False)]
    if missing:
        detail=', '.join(missing)
        print(f'[PAINEL] {key:<8} #{ch.name} ({ch.id}) SEM PERMISSÃO: {detail}')
        return False, f'faltando: {detail}'

    try:
        # Buylist paused: the canonical public panel must not expose a sell button.
        if key=='buylist' and not buylist_enabled():
            view=None
        with Session() as s:
            p=s.get(Panel,(g,key))
        msg=None
        if p:
            # If the panel was moved/reconfigured, do not fetch its old message from the new channel.
            if p.channel_id==ch.id:
                try:
                    msg=await ch.fetch_message(p.message_id)
                except discord.NotFound:
                    msg=None
                except discord.Forbidden:
                    print(f'[PAINEL] {key:<8} #{ch.name} sem acesso ao histórico/mensagem existente')
                    return False, 'sem acesso à mensagem existente'
                except discord.HTTPException as e:
                    print(f'[PAINEL] {key:<8} #{ch.name} falha ao buscar mensagem: {e}')
        if msg:
            await msg.edit(embed=panel_embed(key),view=view)
        else:
            msg=await ch.send(embed=panel_embed(key),view=view)
            with Session.begin() as s:
                s.merge(Panel(guild_id=g,panel_key=key,channel_id=ch.id,message_id=msg.id))
        if key=='buylist' and not buylist_enabled():
            await cleanup_paused_buylist_legacy_panels(g,msg.id)
        print(f'[PAINEL] {key:<8} #{ch.name} ({ch.id}) OK')
        return True, 'ok'
    except discord.Forbidden as e:
        print(f'[PAINEL] {key:<8} #{ch.name} ({ch.id}) 403 Missing Permissions: {e}')
        return False, 'Discord recusou a operação (403 Missing Permissions)'
    except discord.HTTPException as e:
        print(f'[PAINEL] {key:<8} #{ch.name} ({ch.id}) erro HTTP: {e}')
        return False, f'erro Discord HTTP {getattr(e,"status","?")}'
    except Exception as e:
        print(f'[PAINEL] {key:<8} #{ch.name} ({ch.id}) erro inesperado: {type(e).__name__}: {e}')
        return False, f'{type(e).__name__}: {e}'

async def refresh_skin(skin_id):
    with Session() as s:x=s.get(Skin,skin_id)
    if not x or not x.channel_id or not x.message_id:return
    ch=bot.get_channel(x.channel_id)
    try:m=await ch.fetch_message(x.message_id);await m.edit(embed=skin_embed(x),view=SkinPurchaseView(x) if x.status in ('AVAILABLE','RESERVED') else None)
    except:pass

async def reconcile_active_skin_messages(guild_id:int):
    """V3.8.4.9: GET active catalog cards and PATCH only stale/mismatched ones."""
    checked=patched=missing=failed=0
    with Session() as s:
        rows=list(s.scalars(select(Skin).where(Skin.guild_id==guild_id,Skin.status.in_(['AVAILABLE','RESERVED']))).all())
        items=[(x.id,x.code,x.status,x.channel_id,x.message_id) for x in rows if x.channel_id and x.message_id]
    for skin_id,code,status,channel_id,message_id in items:
        checked+=1
        ch=bot.get_channel(int(channel_id))
        if not isinstance(ch,discord.TextChannel):
            failed+=1;continue
        try:
            msg=await ch.fetch_message(int(message_id))
            custom_ids=set()
            for row in getattr(msg,'components',[]) or []:
                for item in getattr(row,'children',[]) or []:
                    cid=getattr(item,'custom_id',None)
                    if cid:custom_ids.add(cid)
            has_edit='v384:skin:edit' in custom_ids
            has_buy='v370:skin:buy' in custom_ids
            expected_buy=(status=='AVAILABLE')
            embed_text=' '.join(str(e.to_dict()) for e in (getattr(msg,'embeds',[]) or []))
            status_ok=(code in embed_text and status in embed_text)
            stale=(not has_edit) or (has_buy != expected_buy) or (not status_ok)
            if stale:
                with Session() as s:x=s.get(Skin,skin_id)
                if x:
                    await msg.edit(embed=skin_embed(x),view=SkinPurchaseView(x))
                    patched+=1
                    print(f'[RESERVED RECONCILE] {code} | status={status} | anúncio atualizado')
        except discord.NotFound:
            missing+=1
            print(f'[RESERVED RECONCILE] {code} | mensagem ausente (404)')
        except Exception as e:
            failed+=1
            print(f'[RESERVED RECONCILE] {code} | falha: {type(e).__name__}: {e}')
    print(f'[RESERVED RECONCILE] checked={checked} | patched={patched} | ausentes={missing} | falhas={failed}')
    return patched

async def post_news(x,source_text='Nova skin disponível'):
    ch=channel(x.guild_id,'news')
    if not isinstance(ch,discord.TextChannel):return
    e=skin_embed(x);e.title='🔥 '+x.name;e.description=f'**{source_text}**\n{x.code} • {x.status}'
    try:await ch.send(embed=e)
    except:pass

async def post_sold(sale,x):
    ch=channel(x.guild_id,'sold')
    if not isinstance(ch,discord.TextChannel):return
    e=discord.Embed(title='🔴 SKIN VENDIDA',description=f'**{x.name}**\n{x.code} • {x.exterior or "—"}',color=0xED4245)
    e.add_field(name='Valor',value=money(sale.sale_price));e.set_footer(text='CLUTCH CLUB • negociação concluída')
    try:await ch.send(embed=e)
    except:pass

async def invite_feedback(sale):
    try:
        u=bot.get_user(sale.buyer_id) or await bot.fetch_user(sale.buyer_id)
        await u.send(f'⭐ Sua compra **{sale.code}** foi concluída. Se quiser, avalie sua experiência com a Clutch Club.',view=VerifiedFeedbackView(sale.code))
    except:pass

async def process_expired_sale_reservations():
    """Repair expired/orphan RESERVED skins, including reservations created before V3.8.4.6."""
    now=datetime.now(timezone.utc)
    candidates=[]
    with Session() as s:
        skins=list(s.scalars(select(Skin).where(Skin.status=='RESERVED')).all())
        print(f'[RESERVATION SCAN] {len(skins)} skin(s) RESERVED encontrada(s).')
        for skin in skins:
            sale=s.scalar(select(Sale).where(Sale.skin_id==skin.id).order_by(Sale.id.desc()))
            print(f'[RESERVATION SCAN] {skin.code} | skin_until={skin.reserved_until} | sale={getattr(sale,"code",None)} | sale_status={getattr(sale,"status",None)} | sale_until={getattr(sale,"reserved_until",None)}')
            # Never auto-release a transaction that reached a protected payment/trade stage.
            if sale and sale.status in ('PAYMENT_CONFIRMED','TRADE_SENT','COMPLETED'):
                continue
            if sale and sale.status=='CANCELLED':
                candidates.append((skin.guild_id,skin.id,sale.code,'REPAIR_CANCELLED'))
                continue
            if sale and sale.status=='RESERVED':
                deadlines=[d for d in (utc_aware(sale.reserved_until),utc_aware(skin.reserved_until),(utc_aware(sale.created_at)+timedelta(minutes=RESERVATION_MINUTES)) if sale.created_at else None) if d]
                deadline=min(deadlines) if deadlines else None
                if deadline and deadline<now:candidates.append((skin.guild_id,skin.id,sale.code,'EXPIRED'))
                continue
            # Legacy/orphan RESERVED skin: any non-protected sale state must not keep stock locked forever.
            deadlines=[d for d in (utc_aware(skin.reserved_until),(utc_aware(sale.reserved_until) if sale else None),((utc_aware(sale.created_at)+timedelta(minutes=RESERVATION_MINUTES)) if sale and sale.created_at else None),(utc_aware(skin.created_at)+timedelta(minutes=RESERVATION_MINUTES)) if skin.created_at else None) if d]
            deadline=min(deadlines) if deadlines else None
            if deadline and deadline<now:candidates.append((skin.guild_id,skin.id,getattr(sale,'code',None),'LEGACY_ORPHAN'))
    released=0
    for guild_id,skin_id,sale_code,reason in candidates:
        try:
            if sale_code and reason=='EXPIRED':
                sale,skin=sale_step(guild_id,0,sale_code,'CANCELLED')
            else:
                with Session.begin() as s:
                    skin=s.get(Skin,skin_id)
                    if not skin or skin.status!='RESERVED':continue
                    skin.status='AVAILABLE';skin.reserved_by=None;skin.reserved_until=None
                    log(s,guild_id,0,'RESERVATION_RECOVERY','skin',skin.id,f'{reason}; sale={sale_code or "none"}')
                    skin_code=skin.code
                with Session() as s:skin=s.get(Skin,skin_id)
                sale=None
            await refresh_skin(skin.id)
            if sale_code:
                await refresh_sale_operation(sale_code,guild_id)
                await ticket_notice(guild_id,sale_code,'⏱️ **Reserva expirada automaticamente.** O prazo terminou sem confirmação de pagamento e a skin voltou a ficar disponível no catálogo.')
                await close_negotiation_ticket(guild_id,sale_code,'Reserva expirada automaticamente')
            released+=1
            print(f'[RESERVATION TIMEOUT] {sale_code or "sem VD"} | {skin.code} -> AVAILABLE | motivo={reason} | sem lançamento financeiro')
        except Exception as e:
            print(f'[RESERVATION TIMEOUT] {sale_code or skin_id} falhou: {type(e).__name__}: {e}')
    return released

@tasks.loop(minutes=1)
async def housekeeping():
    await process_expired_sale_reservations()

_startup_done=False
@bot.event
async def on_member_join(member:discord.Member):
    """Individual welcome message. The fixed onboarding panel remains the access gate."""
    if member.bot:return
    ch_id=cfg(member.guild.id,'welcome_channel_id')
    ch=bot.get_channel(int(ch_id)) if ch_id else None
    if not isinstance(ch,discord.TextChannel):
        print(f'[WELCOME] {member} entrou, mas welcome_channel_id não está configurado.')
        return
    try:
        e=discord.Embed(title='👋 BEM-VINDO À CLUTCH CLUB!',description=f'{member.mention}, seja muito bem-vindo(a)!\n\nPara liberar seu acesso à **Loja** e à **Comunidade**, use o botão **ENTRAR PARA O CLUB** no painel deste canal.\n\n📜 Confira **Como Funciona**\n🛡️ Leia **Segurança**\n🤝 Negocie somente pelos canais oficiais.',color=0xF1C40F)
        e.set_footer(text='CLUTCH CLUB • PLAY • TRADE • JOIN THE CLUB.')
        await ch.send(embed=e)
        print(f'[WELCOME] mensagem enviada para {member} ({member.id}) em #{ch.name}.')
    except Exception as e:print(f'[WELCOME] falha para {member}: {type(e).__name__}: {e}')

@bot.event
async def on_ready():
    global _startup_done
    init_db()
    print(f'[CLUTCH] Discord conectado como {bot.user} ({bot.user.id})')
    print('[CLUTCH] Banco de dados OK')
    try:
        from clutch_os.api.app import _database_label
        print(f'[CLUTCH DATA] Discord Bot DB: {_database_label()}')
    except Exception as e:
        print(f'[CLUTCH DATA] Nao foi possivel exibir o caminho do banco: {e}')
    if not _startup_done:
        for v in (PublicPanel(),CatalogPanel(),InterestPanel(),OrderPanel(),ProposalResponseView(),OperationsView(),OrderCustomerView(),OnboardingView(),SkinPurchaseView()):
            bot.add_view(v)
        # V3.7.3: reaplica o botão COMPRAR nos anúncios já existentes do catálogo.
        try:
            with Session() as s:
                catalog_count=len([x.id for x in s.scalars(select(Skin).where(Skin.status.in_(['AVAILABLE','RESERVED']))).all() if x.channel_id and x.message_id])
            print(f'[CATALOG] {catalog_count} anúncio(s) existente(s); PATCH em massa no boot desativado (V3.8.4).')
        except Exception as e:
            print(f'[CATALOG] Aviso ao sincronizar botões de compra: {type(e).__name__}: {e}')
        if not housekeeping.is_running():
            housekeeping.start()
        # V3.8.4.6: recover reservations that expired while the bot was offline/redeploying.
        recovered=await process_expired_sale_reservations()
        if recovered:
            print(f'[RESERVATION TIMEOUT] recovery no boot: {recovered} reserva(s) vencida(s) liberada(s).')
        # V3.8.4.9: reconcile only stale active catalog messages. This repairs legacy RESERVED cards
        # without restoring the old mass-PATCH behavior.
        await reconcile_active_skin_messages(int(GUILD_ID) if GUILD_ID else (bot.guilds[0].id if bot.guilds else 0))
        # V3.4.4.1: Discord Bootstrap Shield. Never let command sync abort on_ready.
        connected_ids=[g.id for g in bot.guilds]
        print(f'[DISCORD] Guilds conectadas: {connected_ids}')
        sync_ok=False
        if GUILD_ID:
            canonical=bot.get_guild(int(GUILD_ID))
            if canonical is None:
                print(f'[DISCORD] AVISO: guild canônica {GUILD_ID} não está entre as guilds conectadas. Sync ignorado; bootstrap continuará.')
            else:
                try:
                    bot.tree.copy_global_to(guild=canonical)
                    synced=await bot.tree.sync(guild=canonical)
                    print(f'[DISCORD] Slash sync OK em {canonical.id}: {len(synced)} comando(s).')
                    sync_ok=True
                except discord.Forbidden as e:
                    print(f'[DISCORD] AVISO: slash sync sem acesso na guild {canonical.id}: {e}. Bootstrap continuará.')
                except discord.NotFound as e:
                    print(f'[DISCORD] AVISO: guild/app não encontrada durante slash sync: {e}. Bootstrap continuará.')
                except discord.HTTPException as e:
                    print(f'[DISCORD] AVISO: falha HTTP no slash sync: {e}. Bootstrap continuará.')
                except Exception as e:
                    print(f'[DISCORD] AVISO: falha inesperada no slash sync ({type(e).__name__}): {e}. Bootstrap continuará.')
        else:
            try:
                synced=await bot.tree.sync()
                print(f'[DISCORD] Slash sync global OK: {len(synced)} comando(s).')
                sync_ok=True
            except Exception as e:
                print(f'[DISCORD] AVISO: slash sync global falhou ({type(e).__name__}): {e}. Bootstrap continuará.')
        _startup_done=True
    warnings=0
    for g in bot.guilds:
        if not await apply_buylist_mode(g.id): warnings+=1
        if AUTO_PUBLISH:
            for k,v in [('buylist',PublicPanel()),('catalog',CatalogPanel()),('interest',InterestPanel()),('order',OrderPanel())]:
                ok,_=await ensure_panel(g.id,k,v)
                if not ok: warnings+=1
            if cfg(g.id,'welcome_channel_id') and not await ensure_onboarding_panel(g.id): warnings+=1
        # One-time SK normalization, then legacy catalog UI migration.
        await normalize_skin_codes_v3844(g.id)
        await migrate_legacy_skin_edit_buttons(g.id)
    for g in bot.guilds:
        access_ok,access_problems,_=customer_access_state(g.id)
        if customer_role(g.id):
            if access_ok:
                public_count=sum(1 for k in public_channel_keys() if isinstance(channel(g.id,k),discord.TextChannel))
                print(f'[ACCESS] Cliente: {public_count} públicos OK | Operations privado OK | Onboarding OK')
            else:
                print('[ACCESS] AVISO: '+' | '.join(access_problems))
    for g in bot.guilds:
        log_customer_member_access(g.id)
    print(f'[CLUTCH] Inicialização concluída com {warnings} aviso(s). Bot permanece online.')

@bot.tree.command(name='configurar-onboarding',description='Configura o canal de entrada e o cargo liberado pelo onboarding')
@app_commands.checks.has_permissions(administrator=True)
async def configurar_onboarding(i:discord.Interaction,canal:discord.TextChannel,cargo:discord.Role):
    if cargo.is_default():return await i.response.send_message('❌ Selecione um cargo de Cliente, não @everyone.',ephemeral=True)
    me=i.guild.me if i.guild else None
    if not me or not me.guild_permissions.manage_roles or cargo>=me.top_role:
        return await i.response.send_message('❌ Coloque o cargo do **Clutch Bot acima do cargo de Cliente** e conceda **Gerenciar Cargos** antes de configurar.',ephemeral=True)
    set_cfg(gid(i),'welcome_channel_id',canal.id);set_cfg(gid(i),'customer_role_id',cargo.id)
    ok=await ensure_onboarding_panel(gid(i))
    access_ok,problems=await repair_customer_access(gid(i))
    if access_ok:
        suffix=' ✅ Acesso final do Cliente verificado: canais públicos liberados e Operations Center protegido.'
    else:
        suffix=' ⚠️ O estado final ainda precisa de correção: '+ ' | '.join(problems)
    await i.response.send_message(f'✅ Onboarding configurado: {canal.mention} → {cargo.mention}. Painel '+('publicado/atualizado.' if ok else 'não pôde ser publicado; confira permissões do canal.')+suffix,ephemeral=True)

@bot.tree.command(name='publicar-onboarding',description='Cria/atualiza o painel ENTRAR PARA O CLUB')
@app_commands.checks.has_permissions(administrator=True)
async def publicar_onboarding(i:discord.Interaction):
    await i.response.defer(ephemeral=True)
    ok=await ensure_onboarding_panel(gid(i))
    await i.followup.send('✅ Painel de onboarding publicado/atualizado.' if ok else '❌ Configure primeiro com `/configurar-onboarding` e confira as permissões.',ephemeral=True)

@bot.tree.command(name='configurar-canal',description='Define um canal operacional do bot')
@app_commands.checks.has_permissions(manage_guild=True)
@app_commands.choices(tipo=[app_commands.Choice(name=n,value=v) for n,v in [('Catálogo','catalog'),('Buylist','buylist'),('Lista de interesse','interest'),('Encomendas','order'),('Avaliações verificadas','feedback'),('Novidades','news'),('Skins vendidas','sold'),('Operations Center','operations')]])
async def configurar_canal(i:discord.Interaction,tipo:app_commands.Choice[str],canal:discord.TextChannel):set_cfg(gid(i),tipo.value+'_channel_id',canal.id);await i.response.send_message(f'✅ {tipo.value} → {canal.mention}',ephemeral=True)

@bot.tree.command(name='publicar-paineis',description='Cria/atualiza os painéis permanentes')
@app_commands.checks.has_permissions(manage_guild=True)
async def publicar(i:discord.Interaction):
    await i.response.defer(ephemeral=True);ok=[];problems=[]
    for k,v in [('buylist',PublicPanel()),('catalog',CatalogPanel()),('interest',InterestPanel()),('order',OrderPanel())]:
        success,detail=await ensure_panel(gid(i),k,v)
        (ok if success else problems).append(k if success else f'{k}: {detail}')
    text='✅ Painéis OK: '+(', '.join(ok) if ok else 'nenhum')
    if problems:text+='\n⚠️ Problemas:\n• '+'\n• '.join(problems)
    await i.followup.send(text,ephemeral=True)

@bot.tree.command(name='corrigir-acesso-clientes',description='Sincroniza as permissões públicas do cargo Cliente')
@app_commands.checks.has_permissions(administrator=True)
async def corrigir_acesso_clientes(i:discord.Interaction):
    await i.response.defer(ephemeral=True)
    ok,problems=await repair_customer_access(gid(i))
    if ok:
        await i.followup.send('✅ Acesso do cargo **Cliente** sincronizado. Canais públicos liberados e Operations Center protegido.',ephemeral=True)
    else:
        await i.followup.send('⚠️ Sincronização parcial. Problemas: '+', '.join(problems),ephemeral=True)

@bot.tree.command(name='diagnostico',description='Verifica banco, canais e permissões do Clutch OS')
@app_commands.checks.has_permissions(manage_guild=True)
async def diagnostico(i:discord.Interaction):
    await i.response.defer(ephemeral=True)
    lines=['🩺 **CLUTCH OS — DIAGNÓSTICO**','Banco de dados: ✅']
    checks=[('Catálogo','catalog'),('Buylist','buylist'),('Lista de interesse','interest'),('Encomendas','order'),('Avaliações','feedback'),('Novidades','news'),('Skins vendidas','sold'),('Operations Center','operations')]
    for label,key in checks:
        ch=channel(gid(i),key)
        if not isinstance(ch,discord.TextChannel):
            lines.append(f'{label}: ⚪ não configurado/canal não encontrado')
            continue
        me=ch.guild.me
        perms=ch.permissions_for(me) if me else None
        required=('view_channel','send_messages','embed_links','read_message_history')
        missing=[x for x in required if not perms or not getattr(perms,x,False)]
        if missing:
            lines.append(f'{label}: ❌ {ch.mention} — faltando: `'+', '.join(missing)+'`')
        else:
            lines.append(f'{label}: ✅ {ch.mention}')
    role=customer_role(gid(i))
    lines.append('\n👤 **ACESSO DO CLIENTE**')
    if not role:
        lines.append('Cargo Cliente: ❌ não configurado/encontrado')
    else:
        lines.append(f'Cargo Cliente: ✅ {role.mention}')
        for label,key in checks:
            ch=channel(gid(i),key)
            if not isinstance(ch,discord.TextChannel):
                continue
            can_view=ch.permissions_for(role).view_channel
            expected=(key!='operations')
            icon='✅' if can_view==expected else '❌'
            expectation='deve ver' if expected else 'deve ficar oculto'
            state='VÊ' if can_view else 'NÃO VÊ'
            lines.append(f'{icon} {label}: Cliente **{state}** {ch.mention} ({expectation})')
        wid=cfg(gid(i),'welcome_channel_id');wch=bot.get_channel(int(wid)) if wid else None
        if isinstance(wch,discord.TextChannel):
            can_view=wch.permissions_for(role).view_channel
            lines.append(f'{"✅" if can_view else "❌"} Boas-vindas: Cliente **{"VÊ" if can_view else "NÃO VÊ"}** {wch.mention}')
    lines.append('\nℹ️ O aviso de Message Content Intent não causa o erro 403; os fluxos atuais usam slash commands, botões e modais.')
    await i.followup.send('\n'.join(lines),ephemeral=True)

@bot.tree.command(name='diagnostico-membro',description='Verifica o acesso efetivo de um membro Cliente aos canais')
@app_commands.checks.has_permissions(administrator=True)
async def diagnostico_membro(i:discord.Interaction,membro:discord.Member):
    await i.response.defer(ephemeral=True)
    lines=[f'🧪 **ACESSO EFETIVO — {membro.display_name}**',f'ID: `{membro.id}`']
    lines.append('Cargos: '+(', '.join(r.mention for r in membro.roles if not r.is_default()) or 'nenhum'))
    targets=[('Catálogo','catalog',True),('Buylist','buylist',True),('Lista de interesse','interest',True),('Encomendas','order',True),('Avaliações','feedback',True),('Novidades','news',True),('Skins vendidas','sold',True),('Operations Center','operations',False)]
    wid=cfg(gid(i),'welcome_channel_id'); welcome=bot.get_channel(int(wid)) if wid else None
    if isinstance(welcome,discord.TextChannel):
        targets.append(('Boas-vindas',None,True))
    for label,key,expected in targets:
        ch=welcome if key is None else channel(gid(i),key)
        if not isinstance(ch,discord.TextChannel):
            lines.append(f'⚪ {label}: não configurado/canal não encontrado')
            continue
        d=member_access_details(membro,ch)
        good=d['effective']==expected
        state='VÊ' if d['effective'] else 'NÃO VÊ'
        lines.append(f'{"✅" if good else "❌"} **{label}**: {state} {ch.mention}')
        if not good:
            roles=', '.join(d['roles']) if d['roles'] else 'inherit'
            lines.append(f'↳ `@everyone={d["everyone"]} | roles={roles} | membro={d["member"]} | admin={d["administrator"]}`')
    lines.append('\nℹ️ Este diagnóstico usa `channel.permissions_for(membro)`: a permissão efetiva da conta real. Não altera nenhuma permissão.')
    await i.followup.send('\n'.join(lines),ephemeral=True)

@bot.tree.command(name='operacoes',description='Mostra a fila operacional pendente')
@app_commands.checks.has_permissions(manage_guild=True)
async def operacoes(i:discord.Interaction):
    with Session() as s:
        rows=s.scalars(select(Operation).where(Operation.guild_id==gid(i),Operation.status.in_(['OPEN','WAITING','ACTION_REQUIRED'])).order_by(Operation.id.desc()).limit(20)).all()
    if not rows:return await i.response.send_message('✅ Nenhuma pendência operacional.',ephemeral=True)
    lines=[f'**{x.ref_code}** • {x.kind} • `{x.status}` • {x.title}' for x in rows]
    await i.response.send_message('📟 **OPERATIONS CENTER**\n'+'\n'.join(lines),ephemeral=True)

@bot.tree.command(name='republicar-operacoes',description='Publica no canal Operations pendências que ficaram somente no banco')
@app_commands.checks.has_permissions(manage_guild=True)
async def republicar_operacoes(i:discord.Interaction):
    await i.response.defer(ephemeral=True);n=0
    with Session() as s:ids=[x.id for x in s.scalars(select(Operation).where(Operation.guild_id==gid(i),Operation.status.in_(['OPEN','WAITING','ACTION_REQUIRED']),Operation.staff_message_id.is_(None))).all()]
    for oid in ids:
        if await publish_operation(oid):n+=1
    await i.followup.send(f'📟 {n} pendência(s) publicada(s) no Operations Center.',ephemeral=True)

@bot.tree.command(name='cadastrar-skin',description='Cadastra uma skin no estoque')
@app_commands.checks.has_permissions(manage_guild=True)
async def cadastrar(i:discord.Interaction,nome:str,exterior:str,float:str,preco:str,custo:str='0',taxas:str='0',pattern:str='',stickers:str='',inspect_link:str='',imagem:discord.Attachment|None=None,imagem_url:str=''):
    await i.response.defer(ephemeral=True)
    if imagem and imagem.content_type and not imagem.content_type.startswith('image/'):
        return await i.followup.send('❌ O arquivo enviado em **imagem** precisa ser uma imagem.',ephemeral=True)
    try:x=create_skin(gid(i),nome,exterior,float,pattern or None,stickers or None,preco,custo,inspect_link or None,fees=taxas)
    except Exception as e:return await i.followup.send(f'❌ {e}',ephemeral=True)
    # V3.7.4: anexo tem prioridade; URL continua disponível como fallback.
    skin_image=(imagem.url if imagem else (imagem_url.strip() or None))
    ch=channel(gid(i),'catalog') or i.channel
    if isinstance(ch,discord.TextChannel):
        with Session.begin() as s:y=s.get(Skin,x.id);y.image_url=skin_image
        with Session() as s:x=s.get(Skin,x.id)
        m=await ch.send(embed=skin_embed(x),view=SkinPurchaseView(x));
        with Session.begin() as s:y=s.get(Skin,x.id);y.channel_id=ch.id;y.message_id=m.id
    await post_news(x,'Acabou de chegar na Clutch Club')
    sent=0
    for mt in matching_interests(x):
        try:u=bot.get_user(mt.user_id) or await bot.fetch_user(mt.user_id);await u.send(f'🔔 Match Clutch Club: **{x.name} {x.exterior}**, {money(x.price)}, código **{x.code}**.');sent+=1
        except:pass
    await i.followup.send(f'✅ **{x.code}** cadastrada. {sent} match(es) avisados.',ephemeral=True)

@bot.tree.command(name='fazer-proposta',description='Faz proposta em uma Buylist')
@app_commands.checks.has_permissions(manage_guild=True)
async def fazer_proposta(i:discord.Interaction,codigo:str,valor:str,validade_horas:int=24):
    try:v=D(valor)
    except:return await i.response.send_message('Valor inválido.',ephemeral=True)
    with Session.begin() as s:
        b=s.scalar(select(Buylist).where(Buylist.guild_id==gid(i),Buylist.code==codigo.upper()).with_for_update())
        if not b or b.status not in ('PENDING','COUNTERED'):return await i.response.send_message('Buylist não encontrada ou fora de análise.',ephemeral=True)
        b.proposal=v;b.status='PROPOSED';b.proposal_expires_at=datetime.now(timezone.utc)+timedelta(hours=max(1,validade_horas));log(s,gid(i),i.user.id,'BUYLIST_PROPOSE','buylist',b.id,str(v));uid=b.user_id
    try:u=bot.get_user(uid) or await bot.fetch_user(uid);await u.send(f'💰 **PROPOSTA CLUTCH CLUB — {codigo.upper()}**\nNossa oferta: **{money(v)}**\nValidade: **{max(1,validade_horas)}h**\nResponda pelos botões abaixo.',view=ProposalResponseView())
    except:pass
    await i.response.send_message(f'✅ Proposta {money(v)} enviada.',ephemeral=True)

@bot.tree.command(name='buylist-etapa',description='Avança uma Buylist aceita até estoque')
@app_commands.checks.has_permissions(manage_guild=True)
@app_commands.choices(etapa=[app_commands.Choice(name=n,value=v) for n,v in [('Skin recebida','RECEIVED'),('PIX pago','PAID'),('Adicionar ao estoque','STOCK') ,('Recusar/encerrar','REJECTED')]])
async def buylist_etapa(i:discord.Interaction,codigo:str,etapa:app_commands.Choice[str],preco_venda:str='0',taxas:str='0'):
    with Session.begin() as s:
        b=s.scalar(select(Buylist).where(Buylist.guild_id==gid(i),Buylist.code==codigo.upper()).with_for_update())
        if not b:return await i.response.send_message('Buylist não encontrada.',ephemeral=True)
        allowed={'ACCEPTED':['RECEIVED','REJECTED'],'RECEIVED':['PAID','REJECTED'],'PAID':['STOCK'],'PENDING':['REJECTED'],'COUNTERED':['REJECTED'],'PROPOSED':['REJECTED']}
        if etapa.value not in allowed.get(b.status,[]):return await i.response.send_message(f'Etapa inválida: {b.status} → {etapa.value}',ephemeral=True)
        if etapa.value=='STOCK':
            x=Skin(code='PENDING',guild_id=gid(i),name=b.skin_name,exterior=b.exterior,floatv=b.floatv,pattern=b.pattern,stickers=b.stickers,status='AVAILABLE',cost=b.proposal or b.counterproposal or b.desired_price or 0,acquisition_fees=D(taxas),price=D(preco_venda),source='BUYLIST',source_ref=b.code);s.add(x);s.flush();x.code=next_skin_code(s,gid(i));b.stock_skin_id=x.id;b.status='COMPLETED';s.add(Ledger(guild_id=gid(i),skin_id=x.id,kind='ACQUISITION',amount=-x.cost,note=b.code));
            if D(taxas):s.add(Ledger(guild_id=gid(i),skin_id=x.id,kind='ACQUISITION_FEE',amount=-D(taxas),note=b.code))
            log(s,gid(i),i.user.id,'BUYLIST_STOCK','buylist',b.id,x.code);sid=x.id
        else:b.status=etapa.value;log(s,gid(i),i.user.id,'BUYLIST_STATUS','buylist',b.id,etapa.value);sid=None
    if sid:
        with Session() as s:x=s.get(Skin,sid)
        ch=channel(gid(i),'catalog')
        if isinstance(ch,discord.TextChannel):
            m=await ch.send(embed=skin_embed(x),view=SkinPurchaseView(x));
            with Session.begin() as s:y=s.get(Skin,sid);y.channel_id=ch.id;y.message_id=m.id
        await post_news(x,'Nova entrada via Buylist')
    await i.response.send_message(f'✅ {codigo.upper()} → {"COMPLETED" if etapa.value=="STOCK" else etapa.value}',ephemeral=True)

@bot.tree.command(name='venda-etapa',description='Avança pagamento/trade/conclusão de uma venda')
@app_commands.checks.has_permissions(manage_guild=True)
@app_commands.choices(etapa=[app_commands.Choice(name=n,value=v) for n,v in [('Pagamento confirmado','PAYMENT_CONFIRMED'),('Trade enviada','TRADE_SENT'),('Concluir venda','COMPLETED'),('Cancelar','CANCELLED')]])
async def venda_etapa(i:discord.Interaction,codigo:str,etapa:app_commands.Choice[str],taxas:str='0'):
    try:
        sale,x=sale_step(gid(i),i.user.id,codigo,etapa.value,taxas);await refresh_skin(x.id)
        if sale.status=='COMPLETED':
            await post_sold(sale,x);await invite_feedback(sale)
        await i.response.send_message(f'✅ {sale.code} → {sale.status}.',ephemeral=True)
    except Exception as e:await i.response.send_message(f'❌ {e}',ephemeral=True)

@bot.tree.command(name='retirar-skin',description='Retira skin para coleção pessoal')
@app_commands.checks.has_permissions(manage_guild=True)
async def retirar(i:discord.Interaction,codigo:str,motivo:str='Coleção pessoal'):
    try:x=transition_skin(gid(i),i.user.id,codigo,'PERSONAL',motivo);await refresh_skin(x.id);await i.response.send_message(f'🏠 {x.code} foi para coleção pessoal. Custo preservado.',ephemeral=True)
    except Exception as e:await i.response.send_message(f'❌ {e}',ephemeral=True)
@bot.tree.command(name='devolver-skin',description='Devolve skin pessoal ao estoque')
@app_commands.checks.has_permissions(manage_guild=True)
async def devolver(i:discord.Interaction,codigo:str):
    try:x=transition_skin(gid(i),i.user.id,codigo,'AVAILABLE','Retorno');await refresh_skin(x.id);await i.response.send_message(f'↩️ {x.code} voltou ao estoque.',ephemeral=True)
    except Exception as e:await i.response.send_message(f'❌ {e}',ephemeral=True)

@bot.tree.command(name='configurar-pagamento',description='Configura PIX usado nas encomendas')
@app_commands.checks.has_permissions(administrator=True)
async def configurar_pagamento(i:discord.Interaction,pix_chave:str,favorecido:str='Clutch Club'):
    set_cfg(gid(i),'pix_key',pix_chave.strip());set_cfg(gid(i),'pix_holder',favorecido.strip() or 'Clutch Club')
    await i.response.send_message('✅ Pagamento configurado. A chave PIX será enviada somente após o cliente aceitar uma proposta e escolher PIX.',ephemeral=True)

@bot.tree.command(name='encomenda-etapa',description='Atualiza uma encomenda e sincroniza o Operations Center')
@app_commands.checks.has_permissions(manage_guild=True)
@app_commands.choices(etapa=[app_commands.Choice(name=ORDER_LABELS[x],value=x) for x in ['SEARCHING','FOUND','PROPOSAL_SENT','PAYMENT_PENDING','PAYMENT_CONFIRMED','AWAITING_ACQUISITION','ACQUIRED','TRADE_LOCK','READY','DELIVERED']]+[app_commands.Choice(name='CANCELADA',value='CANCELLED')])
async def encomenda_etapa(i:discord.Interaction,codigo:str,etapa:app_commands.Choice[str],custo_encontrado:str='',preco_cliente:str='',fornecedor:str='',trade_lock_ate:str=''):
    try:
        if etapa.value=='PROPOSAL_SENT':raise ValueError('Use o Operations Center para registrar a skin e enviar a proposta.')
        if etapa.value=='FOUND':raise ValueError('Use o formulário REGISTRAR SKIN ENCONTRADA no Operations Center.')
        codigo=normalize_order_code(codigo); requested=gid(i); existing=find_order_by_code(codigo,requested)
        if not existing: raise ValueError('Encomenda não encontrada.')
        target=etapa.value
        lock=(trade_lock_ate or '').strip()
        o=advance_order(existing.guild_id,i.user.id,codigo,target)
        with Session.begin() as s:
            x=s.get(Order,o.id)
            if custo_encontrado:x.found_price=D(custo_encontrado)
            if preco_cliente:x.customer_price=D(preco_cliente)
            if fornecedor:x.supplier=fornecedor[:80]
            if target=='TRADE_LOCK':
                if not lock: raise ValueError('Para TRADE LOCK, informe `trade_lock_ate` em DD/MM/AAAA HH:MM ou DD/MM/AAAA.')
                parsed=parse_trade_lock(lock)
                if parsed<=datetime.now(timezone.utc): raise ValueError('A data/hora do Trade Lock precisa estar no futuro.')
                x.trade_lock_until=parsed
            elif target=='READY':
                x.trade_lock_until=None
            elif lock:
                raise ValueError('`trade_lock_ate` só deve ser usado na etapa TRADE LOCK.')
        with Session() as s:o=s.get(Order,o.id)
        await sync_order_operation(o);await notify_order_customer(o)
        await i.response.send_message(f'✅ **{o.code}** → **{order_status_label(o.status)}**.',ephemeral=True)
    except Exception as e:await i.response.send_message(f'❌ {e}',ephemeral=True)

@bot.tree.command(name='resetar-encomendas-teste',description='APAGA encomendas de teste e reinicia ENC-00001')
@app_commands.checks.has_permissions(administrator=True)
async def resetar_encomendas_teste(i:discord.Interaction,confirmacao:str):
    if confirmacao.strip().upper()!='APAGAR TESTES':
        return await i.response.send_message('❌ Cancelado. Para confirmar, digite exatamente: `APAGAR TESTES`.',ephemeral=True)
    from sqlalchemy import delete, text
    from .db import engine
    cg=canonical_order_guild(gid(i))
    with Session.begin() as s:
        order_ids=list(s.scalars(select(Order.id).where(Order.guild_id==cg)).all())
        if order_ids:
            s.execute(delete(NegotiationOrder).where(NegotiationOrder.order_id.in_(order_ids)))
        s.execute(delete(Operation).where(Operation.guild_id==cg,Operation.kind=='ORDER'))
        s.execute(delete(Audit).where(Audit.guild_id==cg,Audit.entity_type=='order'))
        s.execute(delete(Order).where(Order.guild_id==cg))
    # Reinicia somente a sequência de encomendas no SQLite; não toca skins, vendas, financeiro ou configurações.
    if engine.dialect.name=='sqlite':
        from sqlalchemy import inspect
        with engine.begin() as c:
            if 'sqlite_sequence' in inspect(c).get_table_names():
                c.execute(text("DELETE FROM sqlite_sequence WHERE name='orders'"))
    print(f'[RESET TESTES] guild={cg} actor={i.user.id} encomendas apagadas; próxima encomenda será ENC-00001.')
    await i.response.send_message('🧹 Encomendas de teste apagadas. A próxima encomenda será **ENC-00001**. Estoque, vendas, financeiro, painéis e configurações foram preservados.',ephemeral=True)

@bot.tree.command(name='tradein-criar',description='Cria uma negociação com crédito de skins + complemento em dinheiro')
@app_commands.checks.has_permissions(manage_guild=True)
async def tradein_criar(i:discord.Interaction,cliente:discord.Member,valor_venda:str,credito_tradein:str,encomendas:str='',observacoes:str=''):
    try:total=D(valor_venda);credit=D(credito_tradein)
    except:return await i.response.send_message('❌ Valores inválidos.',ephemeral=True)
    if credit<0 or total<0 or credit>total:return await i.response.send_message('❌ Crédito deve ficar entre zero e o valor da venda.',ephemeral=True)
    with Session.begin() as s:
        n=Negotiation(code='PENDING',guild_id=gid(i),user_id=cliente.id,kind='TRADE_IN',status='OPEN',sale_total=total,trade_credit=credit,cash_due=total-credit,notes=observacoes or None);s.add(n);s.flush();n.code=f'NEG-{n.id:05d}'
        linked=[]
        for code in [x.strip().upper() for x in encomendas.split(',') if x.strip()]:
            o=s.scalar(select(Order).where(Order.guild_id==gid(i),Order.code==code))
            if o:s.add(NegotiationOrder(negotiation_id=n.id,order_id=o.id));linked.append(code)
        log(s,gid(i),i.user.id,'TRADEIN_CREATE','negotiation',n.id,f'{n.code}; credit={credit}; cash={total-credit}; orders={linked}')
        nid=n.id;ncode=n.code
    opid=queue_operation(gid(i),'TRADEIN',ncode,nid,cliente.id,f'TRADE-IN — {ncode}',f'**Venda:** {money(total)}\n**Crédito em skins:** {money(credit)}\n**Complemento em dinheiro:** **{money(total-credit)}**\n**Encomendas:** {", ".join(linked) or "—"}\n**Observações:** {observacoes or "—"}','HIGH');await publish_operation(opid)
    await i.response.send_message(f'🔁 **{ncode}** criada. Crédito: **{money(credit)}** • dinheiro a receber: **{money(total-credit)}**.',ephemeral=True)

@bot.tree.command(name='tradein-item',description='Adiciona uma skin recebida a uma negociação Trade-In')
@app_commands.checks.has_permissions(manage_guild=True)
async def tradein_item(i:discord.Interaction,negociacao:str,nome:str,exterior:str,float:str,credito:str,pattern:str=''):
    if not valid_float(float):return await i.response.send_message('❌ Float inválido.',ephemeral=True)
    try:cv=D(credito)
    except:return await i.response.send_message('❌ Crédito inválido.',ephemeral=True)
    with Session.begin() as s:
        n=s.scalar(select(Negotiation).where(Negotiation.guild_id==gid(i),Negotiation.code==negociacao.upper()).with_for_update())
        if not n:return await i.response.send_message('❌ Negociação não encontrada.',ephemeral=True)
        t=TradeInItem(negotiation_id=n.id,code='PENDING',name=nome,exterior=exterior.upper(),floatv=float.replace(',','.'),pattern=pattern or None,credit_value=cv,status='EXPECTED');s.add(t);s.flush();t.code=f'TI-{t.id:05d}';log(s,gid(i),i.user.id,'TRADEIN_ITEM','negotiation',n.id,f'{t.code} {nome} {cv}');code=t.code
    await i.response.send_message(f'✅ **{code}** adicionada à {negociacao.upper()} por **{money(cv)}** de crédito.',ephemeral=True)

@bot.tree.command(name='tradein-receber',description='Confirma recebimento da skin do Trade-In e cria SK-XXXXX')
@app_commands.checks.has_permissions(manage_guild=True)
async def tradein_receber(i:discord.Interaction,item:str,preco_venda:str):
    try:pv=D(preco_venda)
    except:return await i.response.send_message('❌ Preço inválido.',ephemeral=True)
    with Session.begin() as s:
        t=s.scalar(select(TradeInItem).where(TradeInItem.code==item.upper()).with_for_update())
        if not t or t.status!='EXPECTED':return await i.response.send_message('❌ Item não encontrado ou já recebido.',ephemeral=True)
        n=s.get(Negotiation,t.negotiation_id)
        if n.guild_id!=gid(i):return await i.response.send_message('❌ Item não pertence a este servidor.',ephemeral=True)
        x=Skin(code='PENDING',guild_id=gid(i),name=t.name,exterior=t.exterior,floatv=t.floatv,pattern=t.pattern,status='AVAILABLE',cost=t.credit_value,acquisition_fees=0,price=pv,source='TRADE_IN',source_ref=n.code);s.add(x);s.flush();x.code=next_skin_code(s,gid(i));t.stock_skin_id=x.id;t.status='RECEIVED';s.add(Ledger(guild_id=gid(i),skin_id=x.id,kind='TRADE_IN_ASSET',amount=0,note=f'{n.code} • custo-base {t.credit_value}'));log(s,gid(i),i.user.id,'TRADEIN_RECEIVED','skin',x.id,f'{t.code} -> {x.code}');sid=x.id;scode=x.code
    with Session() as s:x=s.get(Skin,sid)
    ch=channel(gid(i),'catalog')
    if isinstance(ch,discord.TextChannel):
        m=await ch.send(embed=skin_embed(x),view=SkinPurchaseView(x));
        with Session.begin() as s:y=s.get(Skin,sid);y.channel_id=ch.id;y.message_id=m.id
    await post_news(x,'Nova entrada via Trade-In')
    await i.response.send_message(f'📦 **{item.upper()}** recebida → estoque **{scode}**. Custo-base preservado em **{money(x.cost)}**.',ephemeral=True)

@bot.tree.command(name='tradein-pagamento',description='Registra complemento em dinheiro recebido em uma negociação')
@app_commands.checks.has_permissions(manage_guild=True)
async def tradein_pagamento(i:discord.Interaction,negociacao:str,valor:str,referencia:str='PIX'):
    try:v=D(valor)
    except:return await i.response.send_message('❌ Valor inválido.',ephemeral=True)
    with Session.begin() as s:
        n=s.scalar(select(Negotiation).where(Negotiation.guild_id==gid(i),Negotiation.code==negociacao.upper()).with_for_update())
        if not n:return await i.response.send_message('❌ Negociação não encontrada.',ephemeral=True)
        s.add(NegotiationPayment(negotiation_id=n.id,kind='CASH',amount=v,status='CONFIRMED',reference=referencia));n.cash_received=(n.cash_received or 0)+v;s.add(Ledger(guild_id=gid(i),kind='TRADEIN_CASH',amount=v,note=n.code));log(s,gid(i),i.user.id,'TRADEIN_PAYMENT','negotiation',n.id,str(v));received=n.cash_received;due=n.cash_due
        if received>=due:n.status='SETTLED'
    await i.response.send_message(f'💵 {money(v)} registrado em **{negociacao.upper()}**. Recebido: **{money(received)} / {money(due)}**.',ephemeral=True)

@bot.tree.command(name='analisar-compra',description='Aplica as regras configuradas de compra')
async def analisar(i:discord.Interaction,valor_compra:str,venda_rapida:str,taxas:str='0',liquidez:str='Média',caixa:str='0'):
    if not staff(i.user):return await i.response.send_message('Somente a equipe.',ephemeral=True)
    a=intelligence(valor_compra,venda_rapida,taxas,liquidez,caixa if D(caixa)>0 else None);e=discord.Embed(title='🤖 ANÁLISE DE COMPRA',color=0x57F287 if a['meets'] else 0xED4245);e.add_field(name='Lucro líquido projetado',value=money(a['profit']));e.add_field(name='ROI',value=f'{a["roi"]:.1f}%');e.add_field(name='Liquidez informada',value=liquidez);e.add_field(name='Critérios',value='🟢 Atende aos critérios configurados' if a['meets'] else '🔴 Não atende a todos os critérios configurados',inline=False)
    if a['impact'] is not None:e.add_field(name='Impacto no caixa',value=f'{a["impact"]:.1f}%')
    await i.response.send_message(embed=e,ephemeral=True)

@bot.tree.command(name='painel',description='Control Center da operação')
async def painel(i:discord.Interaction):
    if not staff(i.user):return await i.response.send_message('Somente a equipe.',ephemeral=True)
    d=dashboard(gid(i));e=discord.Embed(title='👑 CLUTCH CONTROL CENTER',description='V3.3.1 • Proposal Workflow',color=0x2B2D31);e.add_field(name='📦 Estoque',value=f'🟢 {d["available"]} disponíveis\n🟡 {d["reserved"]} reservadas\n🔴 {d["sold"]} vendidas\n🎒 {d["personal"]} pessoais');e.add_field(name='💵 Financeiro',value=f'Caixa líquido: **{money(d["cash"])}**\nCapital em estoque: **{money(d["capital"])}**\nVenda potencial: **{money(d["stock_value"])}**\nReceita: **{money(d["revenue"])}**\nLucro realizado/acumulado: **{money(d["profit"])}**');e.add_field(name='📌 Operação',value=f'Buylists pendentes: **{d["pending_buylist"]}**\nReputação: **{d["rating"]:.1f}/5** ({d["feedbacks"]})',inline=False);await i.response.send_message(embed=e,ephemeral=True)

@bot.tree.error
async def error(i,e):
    m='Esse comando é administrativo.' if isinstance(e,app_commands.MissingPermissions) else f'❌ {e}'
    try:await i.response.send_message(m,ephemeral=True)
    except:await i.followup.send(m,ephemeral=True)
if __name__=='__main__':
    if not TOKEN:raise RuntimeError('DISCORD_TOKEN não configurado.')
    init_db();bot.run(TOKEN)
