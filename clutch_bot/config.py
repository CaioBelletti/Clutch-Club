import os
from dotenv import load_dotenv
load_dotenv()
def i(k,d=0):
    try:return int(os.getenv(k,str(d)) or d)
    except:return d
TOKEN=os.getenv('DISCORD_TOKEN','').strip();GUILD_ID=i('GUILD_ID');DATABASE_URL=os.getenv('DATABASE_URL','sqlite:///clutch_v2.db').strip();STAFF_ROLE_ID=i('STAFF_ROLE_ID');AUTO_PUBLISH=os.getenv('AUTO_PUBLISH_PANELS','true').lower() in ('1','true','yes','sim');RESERVATION_MINUTES=i('RESERVATION_MINUTES',30)
