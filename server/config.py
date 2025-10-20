from pathlib import Path
from datetime import timezone, timedelta


ROOT = Path(__file__).parent
USERDATA = Path(ROOT/"devdata") # development
#USERDATA = Path("/var/lib/smandacikpus/content/") # production
TEACHERJSON = USERDATA / "teachers.json"
LOGINJSON = USERDATA / "login.json"
DB_FILE = USERDATA / "data.db"
PAGEDIR = USERDATA / "pages"
PREVIEWLIMIT = 10
PREVIEWWORD = 10

ADMIN_REGISTER_TOKEN = "sman2cikpus@admin"

# Session lifetime (days) when 'remember me' is checked
SESSION_LIFETIME_DAYS = 30


# timezone placeholder if needed elsewhere
UTC = timezone.utc
WIB = timezone(timedelta(hours=7), "WIB")