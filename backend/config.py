import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env file from project root or backend directory if present
load_dotenv()

_CURRENT_DIR = Path(__file__).resolve().parent
_PARENT_DIR = _CURRENT_DIR.parent

# Resilient directory resolution: works seamlessly under local dev, monorepos, and Vercel Services
if (_CURRENT_DIR / "frontend").exists() and not (_PARENT_DIR / "frontend").exists():
    BASE_DIR = _CURRENT_DIR
    BACKEND_DIR = _CURRENT_DIR
    FRONTEND_DIR = _CURRENT_DIR / "frontend"
    STATIC_DIR = _CURRENT_DIR / "static"
else:
    BASE_DIR = _PARENT_DIR
    BACKEND_DIR = _CURRENT_DIR
    FRONTEND_DIR = (_CURRENT_DIR / "frontend") if (_CURRENT_DIR / "frontend").exists() else (_PARENT_DIR / "frontend")
    STATIC_DIR = (_CURRENT_DIR / "static") if (_CURRENT_DIR / "static").exists() else (_PARENT_DIR / "static")

# Robust detection of serverless / read-only environment
IS_SERVERLESS = (
    bool(os.getenv("VERCEL"))
    or bool(os.getenv("VERCEL_ENV"))
    or bool(os.getenv("AWS_LAMBDA_FUNCTION_NAME"))
    or bool(os.getenv("LAMBDA_TASK_ROOT"))
)

# Test if local base directory is writable
def _check_writable(dir_path: Path) -> bool:
    try:
        test_file = dir_path / ".test_write_perm"
        test_file.touch()
        test_file.unlink()
        return True
    except Exception:
        return False

is_writable = _check_writable(BASE_DIR)

import tempfile

def normalize_database_url(url: str) -> str:
    """Normalizes Postgres/Supabase URLs for SQLAlchemy compatibility."""
    if not url:
        return ""
    clean = url.strip().strip("'").strip('"')
    if clean.startswith("postgres://"):
        clean = "postgresql://" + clean[len("postgres://"):]
    return clean

# Check Supabase / PostgreSQL environment variables
raw_remote_db = (
    os.getenv("SUPABASE_DB_URL", "").strip()
    or os.getenv("POSTGRES_URL", "").strip()
    or os.getenv("POSTGRES_PRISMA_URL", "").strip()
    or os.getenv("POSTGRES_URL_NON_POOLING", "").strip()
    or os.getenv("DATABASE_URL", "").strip()
)

if IS_SERVERLESS or not is_writable:
    # On serverless (Vercel, AWS Lambda) or read-only container, only /tmp (or system temp) is writable
    TMP_DIR = Path("/tmp") if (os.name != "nt" or Path("/tmp").exists()) else Path(tempfile.gettempdir())
    AUDIO_DIR = TMP_DIR / "audio"
    PDFS_DIR = TMP_DIR / "pdfs"
    default_db_file = TMP_DIR / "zotero_audio.db"
    initial_db = BASE_DIR / "zotero_audio.db"
    if initial_db.exists() and not default_db_file.exists():
        try:
            import shutil
            # copyfile copies contents without copying read-only permission bits
            shutil.copyfile(initial_db, default_db_file)
            try:
                os.chmod(default_db_file, 0o666)
            except Exception:
                pass
        except Exception:
            pass

    # If an external database (Supabase, PostgreSQL, MySQL) is configured, prioritize it!
    if raw_remote_db and not raw_remote_db.startswith("sqlite"):
        DATABASE_URL = normalize_database_url(raw_remote_db)
    else:
        DATABASE_URL = f"sqlite:///{default_db_file.as_posix()}"
else:
    AUDIO_DIR = STATIC_DIR / "audio"
    PDFS_DIR = STATIC_DIR / "pdfs"
    if raw_remote_db and not raw_remote_db.startswith("sqlite"):
        DATABASE_URL = normalize_database_url(raw_remote_db)
    else:
        sqlite_env = os.getenv("DATABASE_URL", "").strip()
        if sqlite_env and not sqlite_env.startswith("sqlite:///./"):
            DATABASE_URL = sqlite_env
        else:
            DATABASE_URL = f"sqlite:///{BASE_DIR / 'zotero_audio.db'}"

# Ensure directories exist safely without raising uncaught exceptions
try:
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    PDFS_DIR.mkdir(parents=True, exist_ok=True)
except Exception:
    pass

# ProfFeb Platform Metadata
APP_NAME = "ProfFeb"
APP_TAGLINE = "The Global Neural Audio Research Workstation & AI Academic Mentor"

# Vercel Services Internal Binding
BACKEND_URL = os.getenv("BACKEND_URL", "").strip().rstrip("/")

# Supabase Configuration (Multi-Tenant Auth & Storage)
SUPABASE_URL = os.getenv("SUPABASE_URL", "https://lbwdlisjvrlbfqonioed.supabase.co").strip()
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Imxid2RsaXNqdnJsYmZxb25pb2VkIiwicm9sZSI6ImFub24iLCJpYXQiOjE3OTU0NDg0NDksImV4cCI6MjExMTAyNDQ0OX0.HpHr1J7UHEI49Oekk_Wzlo050MI5KukHaU1b-NQvN6g").strip()

# Gemini API Configuration
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

# Zotero API Configuration (Optional Global Fallback)
ZOTERO_LIBRARY_ID = os.getenv("ZOTERO_LIBRARY_ID", "")
ZOTERO_API_KEY = os.getenv("ZOTERO_API_KEY", "")
ZOTERO_LIBRARY_TYPE = os.getenv("ZOTERO_LIBRARY_TYPE", "user")

# Text-to-Speech Configuration (edge-tts voices)
DEFAULT_TTS_VOICE = os.getenv("DEFAULT_TTS_VOICE", "en-NG-AbeoNeural")

# GitHub Personal Access Token (PAT) for Autonomous Co-Pilot Execution
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "").strip()
GITHUB_USERNAME = os.getenv("GITHUB_USERNAME", "").strip()

AVAILABLE_VOICES = [
    {"id": "en-NG-AbeoNeural", "name": "🇬🇭 Abeo (West Africa / Ghana - Male, Expressive & Natural)", "gender": "Male", "region": "Africa"},
    {"id": "en-NG-EzinneNeural", "name": "🇬🇭 Ezinne (West Africa / Ghana - Female, Melodic & Clear)", "gender": "Female", "region": "Africa"},
    {"id": "en-KE-ChilembaNeural", "name": "🇰🇪 Chilemba (East Africa / Kenya - Male, Scholarly)", "gender": "Male", "region": "Africa"},
    {"id": "en-KE-AsiliaNeural", "name": "🇰🇪 Asilia (East Africa / Kenya - Female, Articulate)", "gender": "Female", "region": "Africa"},
    {"id": "en-ZA-LukeNeural", "name": "🇿🇦 Luke (South Africa - Male, Crisp & Modern)", "gender": "Male", "region": "Africa"},
    {"id": "en-ZA-LeahNeural", "name": "🇿🇦 Leah (South Africa - Female, Warm)", "gender": "Female", "region": "Africa"},
    {"id": "en-TZ-ElimuNeural", "name": "🇹🇿 Elimu (Tanzania - Male, Calm & Clear)", "gender": "Male", "region": "Africa"},
    {"id": "en-US-ChristopherNeural", "name": "🇺🇸 Christopher (US - Authoritative, Mentor)", "gender": "Male", "region": "US"},
    {"id": "en-US-JennyNeural", "name": "🇺🇸 Jenny (US - Warm, Engaging)", "gender": "Female", "region": "US"},
    {"id": "en-US-GuyNeural", "name": "🇺🇸 Guy (US - Natural, Conversational)", "gender": "Male", "region": "US"},
    {"id": "en-US-AriaNeural", "name": "🇺🇸 Aria (US - Professional, Clear)", "gender": "Female", "region": "US"},
    {"id": "en-GB-RyanNeural", "name": "🇬🇧 Ryan (UK - Academic, Articulate)", "gender": "Male", "region": "UK"},
    {"id": "en-GB-SoniaNeural", "name": "🇬🇧 Sonia (UK - Formal, Scholarly)", "gender": "Female", "region": "UK"},
    {"id": "en-AU-WilliamNeural", "name": "🇦🇺 William (Australia - Relaxed, Direct)", "gender": "Male", "region": "AU"},
    {"id": "en-IN-PrabhatNeural", "name": "🇮🇳 Prabhat (India - Professional, Articulate)", "gender": "Male", "region": "India"},
    {"id": "en-IN-NeerjaNeural", "name": "🇮🇳 Neerja (India - Melodic, Clear)", "gender": "Female", "region": "India"},
    {"id": "en-CA-LiamNeural", "name": "🇨🇦 Liam (Canada - Calm & Modern)", "gender": "Male", "region": "Canada"},
    {"id": "en-IE-ConnorNeural", "name": "🇮🇪 Connor (Ireland - Scholarly & Warm)", "gender": "Male", "region": "Ireland"},
]

