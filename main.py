import os
import sys
import json
import shutil
import asyncio
import logging
import httpx
from datetime import datetime
from pathlib import Path

# Ensure root and backend directories are in sys.path
_CURRENT_DIR = Path(__file__).resolve().parent
_ROOT_DIR = _CURRENT_DIR.parent
if str(_ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(_ROOT_DIR))
if str(_CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(_CURRENT_DIR))

from typing import List, Optional, Dict, Any
from fastapi import FastAPI, Depends, HTTPException, Query, UploadFile, File, Form, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse, HTMLResponse, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import or_, desc, func

try:
    import pypdf
except (ImportError, Exception):
    pypdf = None

try:
    import fitz  # PyMuPDF
except (ImportError, Exception):
    fitz = None

try:
    from backend.config import (
        BASE_DIR, FRONTEND_DIR, STATIC_DIR, AUDIO_DIR, PDFS_DIR,
        GEMINI_API_KEY, GEMINI_MODEL, ZOTERO_LIBRARY_ID, ZOTERO_API_KEY,
        ZOTERO_LIBRARY_TYPE, DEFAULT_TTS_VOICE, AVAILABLE_VOICES, IS_SERVERLESS, is_writable,
        DATABASE_URL, normalize_database_url,
        APP_NAME, APP_TAGLINE, SUPABASE_URL, SUPABASE_KEY
    )
    from backend.database import init_db, get_db, Paper
    from backend.zotero_sync import ZoteroSyncService
    from backend.processor import (
        PDFProcessor, GeminiSummarizer, AudioSynthesizer,
        parse_briefing_sections, extract_document_chapters
    )
    from backend.conference_scout import ConferenceScoutService
    from backend.academic_engines import (
        ResearchGapService, ReviewerSimulatorService,
        FundingScoutService, IndustryLabService
    )
    try:
        from backend.auth import get_current_user, require_current_user
    except Exception:
        get_current_user = None
        require_current_user = None
    try:
        from backend.twin_agent import TwinAgentService, PortfolioSyncService, GitHubConnectorService
    except Exception as _e:
        TwinAgentService = None
        PortfolioSyncService = None
        GitHubConnectorService = None
except ImportError:
    from config import (
        BASE_DIR, FRONTEND_DIR, STATIC_DIR, AUDIO_DIR, PDFS_DIR,
        GEMINI_API_KEY, GEMINI_MODEL, ZOTERO_LIBRARY_ID, ZOTERO_API_KEY,
        ZOTERO_LIBRARY_TYPE, DEFAULT_TTS_VOICE, AVAILABLE_VOICES, IS_SERVERLESS, is_writable,
        DATABASE_URL, normalize_database_url,
        APP_NAME, APP_TAGLINE, SUPABASE_URL, SUPABASE_KEY
    )
    from database import init_db, get_db, Paper
    from zotero_sync import ZoteroSyncService
    from processor import (
        PDFProcessor, GeminiSummarizer, AudioSynthesizer,
        parse_briefing_sections, extract_document_chapters
    )
    from conference_scout import ConferenceScoutService
    from academic_engines import (
        ResearchGapService, ReviewerSimulatorService,
        FundingScoutService, IndustryLabService
    )
    try:
        from auth import get_current_user, require_current_user
    except Exception:
        get_current_user = None
        require_current_user = None
    try:
        from twin_agent import TwinAgentService, PortfolioSyncService, GitHubConnectorService
    except Exception as _e:
        TwinAgentService = None
        PortfolioSyncService = None
        GitHubConnectorService = None

logger = logging.getLogger("api")

# Active processing tasks tracking: paper_id -> {"current": int, "total": int, "percent": int, "status": str}
ACTIVE_SYNTHESIS_PROGRESS = {}
ACTIVE_SYNTHESIS_LOCK = set()
logging.basicConfig(level=logging.INFO)

# Initialize database schema safely without crashing serverless cold starts
try:
    init_db()
except Exception as e:
    logger.warning(f"Database initialization warning: {e}")

app = FastAPI(
    title="Zotero Audio Mentor API",
    description="Transforms Zotero reference library research papers into conversational audio briefings.",
    version="1.0.0"
)

# Enable CORS for frontend integrations
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Pydantic Request Schemas
class SyncRequest(BaseModel):
    library_id: Optional[str] = None
    library_type: Optional[str] = "user"
    api_key: Optional[str] = None
    limit: Optional[int] = 25


class ProcessRequest(BaseModel):
    mode: Optional[str] = "summary"  # "summary" or "full_paper"
    voice: Optional[str] = None
    gemini_api_key: Optional[str] = None
    gemini_model: Optional[str] = None
    scope: Optional[str] = "article"  # "article" (complete paper up to References) or "all"


class SwitchModeRequest(BaseModel):
    mode: str  # "summary" or "full_paper"


class SettingsUpdateRequest(BaseModel):
    gemini_api_key: Optional[str] = None
    gemini_model: Optional[str] = None
    zotero_library_id: Optional[str] = None
    zotero_api_key: Optional[str] = None
    zotero_library_type: Optional[str] = None
    default_voice: Optional[str] = None


class ConferenceSearchRequest(BaseModel):
    query: Optional[str] = ""
    year: Optional[int] = None
    doctoral_only: Optional[bool] = False
    grants_only: Optional[bool] = False
    region: Optional[str] = None
    upcoming_only: Optional[bool] = True


class ConferenceWatchlistRequest(BaseModel):
    conference_name: str
    acronym: str
    core_rank: Optional[str] = None
    submission_deadline: Optional[str] = None
    location: Optional[str] = None


class RadarAnalysisRequest(BaseModel):
    topic: str
    idea_proposal: Optional[str] = ""
    target_domain: Optional[str] = "Computer Science"


class ReviewerRequest(BaseModel):
    title: str
    abstract: str
    methodology: Optional[str] = ""
    target_venue: Optional[str] = "NeurIPS / IEEE"


class FundingSearchRequest(BaseModel):
    query: Optional[str] = ""
    research_work: Optional[str] = ""
    destination: Optional[str] = "All"
    category: Optional[str] = "All"


class LabSearchRequest(BaseModel):
    query: Optional[str] = ""
    research_work: Optional[str] = ""
    location: Optional[str] = "All"
    item_type: Optional[str] = "All"


class TwinSyncRequest(BaseModel):
    url: Optional[str] = "https://febmac.vercel.app"


class TwinUpdateRequest(BaseModel):
    custom_notes: Optional[str] = None
    active_focus: Optional[str] = None


class TwinApplyGrantRequest(BaseModel):
    grant_title: str
    grant_details: Optional[Dict[str, Any]] = {}


class TwinApplyLabRequest(BaseModel):
    lab_title: str
    lab_details: Optional[Dict[str, Any]] = {}


class TwinChatRequest(BaseModel):
    message: str
    history: Optional[List[Dict[str, str]]] = []


class GitHubConnectRequest(BaseModel):
    token: str
    username: Optional[str] = "Febiri"


class PrepareApplicationRequest(BaseModel):
    opportunity_type: str = "grant"  # "grant" or "lab"
    title: str
    details: Optional[Dict[str, Any]] = {}


class DispatchApplicationRequest(BaseModel):
    packet: Dict[str, Any]
    target_repo: Optional[str] = "febPhD"


class PaperChatRequest(BaseModel):
    message: str
    history: Optional[List[Dict[str, str]]] = []


class PaperNoteRequest(BaseModel):
    id: Optional[str] = None
    title: Optional[str] = "Professional Note"
    content: str
    quote: Optional[str] = ""
    category: Optional[str] = "Methodology"
    color: Optional[str] = "yellow"
    created_at: Optional[str] = None


class VoiceChangeRequest(BaseModel):
    voice: str
    mode: Optional[str] = "summary"  # "summary" or "full_paper"


class DatabaseConfigRequest(BaseModel):
    database_url: str


class ReviewerChatRequest(BaseModel):
    paper_title: str
    critique: Optional[Dict[str, Any]] = {}
    message: str
    history: Optional[List[Dict[str, str]]] = []


class RadarChatRequest(BaseModel):
    topic: str
    radar_result: Optional[Dict[str, Any]] = {}
    message: str
    history: Optional[List[Dict[str, str]]] = []


# Core Pipeline Execution Helper
async def execute_processing_pipeline(
    paper_id: int,
    mode: str = "summary",
    voice: Optional[str] = None,
    gemini_key: Optional[str] = None,
    gemini_model: Optional[str] = None,
    scope: Optional[str] = "article",
    db: Session = None
):
    if paper_id in ACTIVE_SYNTHESIS_LOCK:
        logger.info(f"Paper {paper_id} is already actively synthesizing. Skipping duplicate call.")
        return

    ACTIVE_SYNTHESIS_LOCK.add(paper_id)
    ACTIVE_SYNTHESIS_PROGRESS[paper_id] = {
        "current": 0,
        "total": 1,
        "percent": 0,
        "status": "Starting synthesis...",
        "mode": mode
    }
    """
    Executes either:
    - mode="summary": extraction -> Gemini AI 4-part mentor script -> Edge-TTS synthesis
    - mode="full_paper": extraction -> speech sanitization of full text -> Edge-TTS long synthesis
    """
    close_db_at_end = False
    if db is None:
        try:
            from backend.database import SessionLocal
        except ImportError:
            from database import SessionLocal
        db = SessionLocal()
        close_db_at_end = True

    try:
        paper = db.query(Paper).filter(Paper.id == paper_id).first()
        if not paper:
            logger.error(f"Paper ID {paper_id} not found for processing.")
            return

        paper.status = "Processing"
        paper.error_message = None
        db.commit()

        selected_voice = voice or paper.voice_used or DEFAULT_TTS_VOICE

        if mode == "full_paper":
            # --- 100% VERBATIM FULL PAPER READING PIPELINE ---
            logger.info(f"Processing Paper ID {paper.id} in 100% VERBATIM FULL PAPER mode (no words omitted or replaced)...")
            
            # Extract complete verbatim text with PyMuPDF
            if paper.pdf_path and os.path.exists(paper.pdf_path):
                verbatim_text, total_p = PDFProcessor.extract_verbatim_text(paper.pdf_path, scope=scope or "article")
            else:
                verbatim_text = paper.abstract or paper.title

            cleaned_speech = AudioSynthesizer.prepare_verbatim_for_speech(verbatim_text)
            paper.full_text = verbatim_text
            db.commit()

            def on_progress(current, total):
                pct = int((current / max(1, total)) * 100)
                ACTIVE_SYNTHESIS_PROGRESS[paper_id] = {
                    "current": current,
                    "total": total,
                    "percent": pct,
                    "status": f"Synthesizing audio: Chunk {current}/{total} ({pct}%)",
                    "mode": mode
                }

            audio_filename = f"paper_{paper.id}_full_{paper.zotero_item_key or 'direct'}.mp3"
            audio_path, duration = await AudioSynthesizer.synthesize_long_text_async(
                text=cleaned_speech,
                output_filename=audio_filename,
                voice=selected_voice,
                concurrency=3,
                max_chunk_chars=3000,
                progress_callback=on_progress
            )

            if audio_path and os.path.exists(audio_path):
                file_size = os.path.getsize(audio_path)
                if file_size < 25 * 1024 * 1024:
                    try:
                        paper.full_audio_blob = Path(audio_path).read_bytes()
                    except Exception as b_err:
                        logger.warning(f"Failed to persist full_audio_blob to database: {b_err}")
                else:
                    logger.info(f"Full paper audio is {file_size / (1024*1024):.1f}MB, stored safely on local disk.")

            paper.full_audio_path = f"/api/audio/{audio_filename}"
            paper.full_audio_duration = duration
            paper.audio_path = paper.full_audio_path
            paper.audio_duration = duration
            paper.audio_mode = "full_paper"
            paper.voice_used = selected_voice
            paper.status = "Ready"
            paper.error_message = None
            db.commit()
            logger.info(f"Full verbatim paper audio ready for '{paper.title}' (Duration: {duration}s)")

        else:
            # --- SUMMARY BRIEFING PIPELINE ---
            logger.info(f"Processing Paper ID {paper.id} in SUMMARY BRIEFING mode...")
            # Step 1: Text Extraction for summary
            extracted_text = ""
            if paper.pdf_path and os.path.exists(paper.pdf_path):
                try:
                    extracted_text, _ = PDFProcessor.extract_text(paper.pdf_path, max_pages=25)
                except Exception as e:
                    logger.warning(f"Failed to extract text from PDF {paper.pdf_path}: {e}")
                    extracted_text = paper.abstract or paper.title
            else:
                extracted_text = paper.abstract or paper.title

            summarizer = GeminiSummarizer(
                api_key=gemini_key or os.getenv("GEMINI_API_KEY", GEMINI_API_KEY),
                model=gemini_model or os.getenv("GEMINI_MODEL", GEMINI_MODEL)
            )
            briefing_script = await asyncio.to_thread(
                summarizer.generate_briefing,
                title=paper.title,
                text=extracted_text,
                authors=paper.authors,
                abstract=paper.abstract
            )

            # Parse 4 structured sections
            sections = parse_briefing_sections(briefing_script)

            audio_filename = f"paper_{paper.id}_{paper.zotero_item_key or 'direct'}.mp3"
            audio_path, duration = await AudioSynthesizer.synthesize_audio_async(
                text=briefing_script,
                output_filename=audio_filename,
                voice=selected_voice
            )

            if audio_path and os.path.exists(audio_path):
                try:
                    paper.summary_audio_blob = Path(audio_path).read_bytes()
                except Exception as b_err:
                    logger.warning(f"Failed to persist summary_audio_blob to database: {b_err}")

            paper.summary_text = briefing_script
            paper.summary_problem = sections.get("problem", "")
            paper.summary_methodology = sections.get("methodology", "")
            paper.summary_results = sections.get("results", "")
            paper.summary_limitations = sections.get("limitations", "")
            paper.summary_audio_path = f"/api/audio/{audio_filename}"
            paper.summary_audio_duration = duration
            paper.audio_path = paper.summary_audio_path
            paper.audio_duration = duration
            paper.audio_mode = "summary"
            paper.voice_used = selected_voice
            paper.status = "Ready"
            paper.error_message = None
            db.commit()
            logger.info(f"Summary audio briefing ready for '{paper.title}' (Duration: {duration}s)")

    except Exception as e:
        logger.error(f"Error processing paper {paper_id}: {e}", exc_info=True)
        try:
            db.rollback()
            fresh_paper = db.query(Paper).filter(Paper.id == paper_id).first()
            if fresh_paper:
                fresh_paper.status = "Failed"
                fresh_paper.error_message = str(e)
                db.commit()
        except Exception:
            pass
    finally:
        ACTIVE_SYNTHESIS_LOCK.discard(paper_id)
        ACTIVE_SYNTHESIS_PROGRESS.pop(paper_id, None)
        if close_db_at_end:
            db.close()


# API Endpoints
@app.get("/api/health")
def health_check():
    return {
        "status": "online",
        "service": "ProfFeb",
        "version": "2.0.0",
        "serverless": IS_SERVERLESS
    }


@app.get("/api/config")
def get_saas_config():
    """Returns public configuration for frontend initialization."""
    return {
        "app_name": APP_NAME,
        "tagline": APP_TAGLINE,
        "supabase_url": SUPABASE_URL,
        "supabase_key": SUPABASE_KEY,
        "supabase_anon_key": SUPABASE_KEY,
        "has_zotero": bool(os.getenv("ZOTERO_API_KEY", ZOTERO_API_KEY)),
        "available_voices": AVAILABLE_VOICES,
        "default_voice": DEFAULT_TTS_VOICE,
        "version": "2.0.0"
    }


@app.get("/api/user/zotero")
async def get_user_zotero_config(
    current_user: Optional[Dict[str, Any]] = Depends(get_current_user) if get_current_user else None
):
    """Returns user's saved Zotero credentials status (keys masked) or global defaults."""
    library_id = ""
    library_type = "user"
    has_key = False

    if current_user and SUPABASE_URL and SUPABASE_KEY:
        try:
            user_id = current_user.get("id")
            async with httpx.AsyncClient(timeout=4.0) as client:
                resp = await client.get(
                    f"{SUPABASE_URL.rstrip('/')}/rest/v1/profiles",
                    params={"id": f"eq.{user_id}", "select": "zotero_user_id,zotero_api_key"},
                    headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}
                )
                if resp.status_code == 200 and resp.json():
                    p = resp.json()[0]
                    library_id = p.get("zotero_user_id") or ""
                    has_key = bool(p.get("zotero_api_key"))
        except Exception as e:
            logger.warning(f"Could not load user zotero profile: {e}")

    # Fallback to server environment if not individually set
    if not library_id:
        library_id = os.getenv("ZOTERO_LIBRARY_ID", ZOTERO_LIBRARY_ID or "")
    if not has_key:
        has_key = bool(os.getenv("ZOTERO_API_KEY", ZOTERO_API_KEY or ""))

    return {
        "authenticated": bool(current_user),
        "library_id": library_id,
        "library_type": os.getenv("ZOTERO_LIBRARY_TYPE", ZOTERO_LIBRARY_TYPE or "user"),
        "has_key": has_key,
        "configured": bool(library_id and has_key)
    }


class UserZoteroUpdateRequest(BaseModel):
    library_id: str
    api_key: Optional[str] = None
    library_type: Optional[str] = "user"


@app.post("/api/user/zotero")
async def save_user_zotero_config(
    payload: UserZoteroUpdateRequest,
    current_user: Optional[Dict[str, Any]] = Depends(get_current_user) if get_current_user else None
):
    """Persists user's Zotero credentials to their Supabase profile and verifies connection."""
    lib_id = payload.library_id.strip()
    key = (payload.api_key or "").strip()
    ltype = (payload.library_type or "user").strip()

    if not lib_id:
        raise HTTPException(status_code=400, detail="Zotero User/Library ID is required.")

    # Test credentials first with Zotero API
    test_key = key or os.getenv("ZOTERO_API_KEY", ZOTERO_API_KEY or "")
    if test_key:
        test_service = ZoteroSyncService(library_id=lib_id, library_type=ltype, api_key=test_key)
        test_res = test_service.test_connection()
        if not test_res.get("success"):
            return {
                "success": False,
                "message": f"Zotero verification failed: {test_res.get('message')}"
            }

    saved_to_cloud = False
    if current_user and SUPABASE_URL and SUPABASE_KEY:
        try:
            user_id = current_user.get("id")
            update_data = {"zotero_user_id": lib_id, "updated_at": "now()"}
            if key:
                update_data["zotero_api_key"] = key
            
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.patch(
                    f"{SUPABASE_URL.rstrip('/')}/rest/v1/profiles",
                    params={"id": f"eq.{user_id}"},
                    json=update_data,
                    headers={
                        "apikey": SUPABASE_KEY,
                        "Authorization": f"Bearer {SUPABASE_KEY}",
                        "Content-Type": "application/json",
                        "Prefer": "return=minimal"
                    }
                )
                if resp.status_code in [200, 204]:
                    saved_to_cloud = True
        except Exception as e:
            logger.warning(f"Failed to patch user profile: {e}")

    return {
        "success": True,
        "message": f"Connected to Zotero API successfully for Library ID {lib_id}!",
        "library_id": lib_id,
        "library_type": ltype,
        "saved_to_cloud": saved_to_cloud
    }


@app.get("/api/auth/me")
async def get_auth_me(current_user: Optional[Dict[str, Any]] = Depends(get_current_user) if get_current_user else None):
    """Returns current user status or unauthenticated indicator."""
    if current_user:
        return {
            "authenticated": True,
            "user": current_user
        }
    return {
        "authenticated": False,
        "user": None
    }


class ProfileUpdateRequest(BaseModel):
    full_name: Optional[str] = None
    academic_title: Optional[str] = None
    institution: Optional[str] = None
    research_field: Optional[str] = None
    preferred_voice: Optional[str] = None
    tier: Optional[str] = None


@app.get("/api/user/profile")
async def get_user_profile(
    current_user: Optional[Dict[str, Any]] = Depends(get_current_user) if get_current_user else None,
    db: Session = Depends(get_db)
):
    """Returns comprehensive scholar profile, tier, and research stats."""
    if not current_user:
        return {
            "authenticated": False,
            "user": None,
            "stats": {"papers_synced": 0, "audio_minutes": 0.0, "watchlist_count": 0}
        }

    user_id = current_user.get("id")
    email = current_user.get("email") or ""
    meta = current_user.get("user_metadata") or {}
    user_token = current_user.get("token") or SUPABASE_KEY
    auth_header = f"Bearer {user_token}" if user_token else f"Bearer {SUPABASE_KEY}"

    # Default fallback data from OAuth / metadata
    full_name = meta.get("full_name") or meta.get("name") or email.split("@")[0].replace(".", " ").title()
    academic_title = meta.get("academic_title") or "PhD Scholar"
    avatar_url = meta.get("avatar_url") or meta.get("picture") or ""
    institution = meta.get("institution") or ""
    research_field = meta.get("research_field") or "Computational & Applied Science"
    tier = meta.get("tier") or "scholar"
    preferred_voice = meta.get("preferred_voice") or DEFAULT_TTS_VOICE
    zotero_user_id = meta.get("zotero_user_id") or ""
    has_zotero_key = bool(meta.get("zotero_api_key"))

    # If Supabase is connected, query the persistent profiles table
    if SUPABASE_URL and SUPABASE_KEY and user_id:
        try:
            async with httpx.AsyncClient(timeout=4.0) as client:
                resp = await client.get(
                    f"{SUPABASE_URL.rstrip('/')}/rest/v1/profiles",
                    params={"id": f"eq.{user_id}", "select": "*"},
                    headers={"apikey": SUPABASE_KEY, "Authorization": auth_header}
                )
                if resp.status_code == 200 and resp.json():
                    prof = resp.json()[0]
                    full_name = prof.get("full_name") or full_name
                    academic_title = prof.get("academic_title") or academic_title
                    institution = prof.get("institution") or institution
                    research_field = prof.get("research_field") or research_field
                    tier = prof.get("tier") or tier
                    preferred_voice = prof.get("preferred_voice") or preferred_voice
                    zotero_user_id = prof.get("zotero_user_id") or zotero_user_id
                    has_zotero_key = bool(prof.get("zotero_api_key")) or has_zotero_key
                elif resp.status_code == 200 and not resp.json():
                    # Auto-initialize cloud profile on first login (e.g. Google OAuth)
                    await client.post(
                        f"{SUPABASE_URL.rstrip('/')}/rest/v1/profiles",
                        json={
                            "id": user_id,
                            "email": email,
                            "full_name": full_name,
                            "tier": "scholar",
                            "preferred_voice": preferred_voice
                        },
                        headers={"apikey": SUPABASE_KEY, "Authorization": auth_header, "Content-Type": "application/json", "Prefer": "return=minimal"}
                    )
        except Exception as e:
            logger.warning(f"Error fetching/initializing cloud profile: {e}")

    # Gather real usage metrics from DB
    try:
        paper_count = db.query(func.count(Paper.id)).scalar() or 0
        total_audio_sec = db.query(func.sum(Paper.audio_duration)).scalar() or 0.0
        audio_minutes = round(total_audio_sec / 60.0, 1)
    except Exception:
        paper_count = 0
        audio_minutes = 0.0

    return {
        "authenticated": True,
        "user": {
            "id": user_id,
            "email": email,
            "full_name": full_name,
            "academic_title": academic_title,
            "avatar_url": avatar_url,
            "institution": institution,
            "research_field": research_field,
            "tier": tier,
            "preferred_voice": preferred_voice,
            "zotero_user_id": zotero_user_id,
            "has_zotero_key": has_zotero_key,
            "created_at": current_user.get("created_at")
        },
        "stats": {
            "papers_synced": paper_count,
            "audio_minutes": audio_minutes,
            "watchlist_count": 1
        }
    }


@app.post("/api/user/profile")
async def update_user_profile(
    payload: ProfileUpdateRequest,
    current_user: Optional[Dict[str, Any]] = Depends(get_current_user) if get_current_user else None
):
    """Updates academic profile details in Supabase profiles table and user metadata."""
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required to update profile.")

    user_id = current_user.get("id")
    user_token = current_user.get("token") or SUPABASE_KEY
    auth_header = f"Bearer {user_token}" if user_token else f"Bearer {SUPABASE_KEY}"

    update_data = {"updated_at": "now()"}
    meta_updates = {}
    if payload.full_name is not None:
        name = payload.full_name.strip()
        update_data["full_name"] = name
        meta_updates["full_name"] = name
    if payload.academic_title is not None:
        title = payload.academic_title.strip()
        meta_updates["academic_title"] = title
    if payload.institution is not None:
        inst = payload.institution.strip()
        update_data["institution"] = inst
        meta_updates["institution"] = inst
    if payload.research_field is not None:
        rf = payload.research_field.strip()
        update_data["research_field"] = rf
        meta_updates["research_field"] = rf
    if payload.preferred_voice is not None:
        pv = payload.preferred_voice.strip()
        update_data["preferred_voice"] = pv
        meta_updates["preferred_voice"] = pv
    if payload.tier is not None:
        tr = payload.tier.strip()
        update_data["tier"] = tr
        meta_updates["tier"] = tr

    saved_to_cloud = False
    if SUPABASE_URL and SUPABASE_KEY and user_id:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                # 1. Update Supabase Auth user_metadata
                if meta_updates and user_token and user_token != SUPABASE_KEY:
                    try:
                        await client.put(
                            f"{SUPABASE_URL.rstrip('/')}/auth/v1/user",
                            json={"data": meta_updates},
                            headers={"apikey": SUPABASE_KEY, "Authorization": auth_header}
                        )
                    except Exception as err:
                        logger.warning(f"Note updating Supabase auth metadata: {err}")

                # 2. Patch public.profiles table
                resp = await client.patch(
                    f"{SUPABASE_URL.rstrip('/')}/rest/v1/profiles",
                    params={"id": f"eq.{user_id}"},
                    json=update_data,
                    headers={
                        "apikey": SUPABASE_KEY,
                        "Authorization": auth_header,
                        "Content-Type": "application/json",
                        "Prefer": "return=minimal"
                    }
                )
                if resp.status_code in [200, 204]:
                    saved_to_cloud = True
                elif resp.status_code == 404:
                    # Auto insert if row does not exist yet
                    insert_payload = dict(update_data)
                    insert_payload["id"] = user_id
                    insert_payload["email"] = current_user.get("email") or ""
                    await client.post(
                        f"{SUPABASE_URL.rstrip('/')}/rest/v1/profiles",
                        json=insert_payload,
                        headers={
                            "apikey": SUPABASE_KEY,
                            "Authorization": auth_header,
                            "Content-Type": "application/json",
                            "Prefer": "return=minimal"
                        }
                    )
                    saved_to_cloud = True
        except Exception as e:
            logger.warning(f"Error updating cloud profile: {e}")

    return {
        "success": True,
        "message": "Academic profile updated successfully!",
        "saved_to_cloud": saved_to_cloud,
        "updated": update_data
    }


@app.get("/api/voices")
def get_available_voices():
    """Returns supported natural Microsoft Edge neural TTS voices."""
    return {
        "default": DEFAULT_TTS_VOICE,
        "voices": AVAILABLE_VOICES
    }


@app.get("/api/settings")
def get_settings():
    """Returns current environment / API configurations (keys masked)."""
    gemini_key = os.getenv("GEMINI_API_KEY", GEMINI_API_KEY)
    zotero_key = os.getenv("ZOTERO_API_KEY", ZOTERO_API_KEY)
    zotero_lib = os.getenv("ZOTERO_LIBRARY_ID", ZOTERO_LIBRARY_ID)
    zotero_type = os.getenv("ZOTERO_LIBRARY_TYPE", ZOTERO_LIBRARY_TYPE)

    db_str = (
        os.getenv("SUPABASE_DB_URL")
        or os.getenv("POSTGRES_URL")
        or os.getenv("DATABASE_URL")
        or str(DATABASE_URL)
    )
    is_supabase = "supabase" in db_str.lower()
    is_postgres = "postgres" in db_str.lower()
    db_type = "Supabase PostgreSQL" if is_supabase else ("PostgreSQL" if is_postgres else "Local SQLite")

    return {
        "has_gemini_key": bool(gemini_key),
        "gemini_key_preview": f"{gemini_key[:4]}...{gemini_key[-4:]}" if len(gemini_key) > 8 else ("Configured" if gemini_key else "Not Set"),
        "gemini_model": os.getenv("GEMINI_MODEL", GEMINI_MODEL),
        "has_zotero_key": bool(zotero_key),
        "zotero_library_id": zotero_lib or "",
        "zotero_library_type": zotero_type or "user",
        "default_voice": DEFAULT_TTS_VOICE,
        "database_type": db_type,
        "is_cloud_database": is_supabase or is_postgres,
        "available_voices": AVAILABLE_VOICES,
    }


@app.post("/api/settings/test-database")
def test_database_connection(payload: DatabaseConfigRequest):
    """Test connection and writability of a Supabase / PostgreSQL or SQLite database URL."""
    url = payload.database_url.strip()
    if not url:
        return {"success": False, "message": "Database connection URL cannot be empty."}

    norm_url = normalize_database_url(url)
    try:
        from sqlalchemy import create_engine, text
        test_eng = create_engine(
            norm_url,
            connect_args={"check_same_thread": False} if norm_url.startswith("sqlite") else {},
            pool_pre_ping=True
        )
        with test_eng.begin() as conn:
            conn.execute(text("CREATE TABLE IF NOT EXISTS _zam_test (id INTEGER PRIMARY KEY)"))
            conn.execute(text("DROP TABLE IF EXISTS _zam_test"))
            try:
                res = conn.execute(text("SELECT COUNT(*) FROM papers"))
                paper_count = res.scalar() or 0
            except Exception:
                paper_count = 0

        db_type = "Supabase PostgreSQL" if "supabase" in norm_url.lower() else ("PostgreSQL" if "postgres" in norm_url.lower() else "SQLite")
        return {
            "success": True,
            "database_type": db_type,
            "paper_count": paper_count,
            "message": f"Connected to {db_type} successfully! Verified write privileges ({paper_count} papers currently stored)."
        }
    except Exception as e:
        return {
            "success": False,
            "message": f"Database connection error: {str(e)}"
        }


@app.post("/api/settings/test-zotero")
def test_zotero_connection(req: SyncRequest):
    """Test Zotero credentials without performing a full sync."""
    service = ZoteroSyncService(
        library_id=req.library_id,
        library_type=req.library_type,
        api_key=req.api_key
    )
    result = service.test_connection()
    return result


@app.post("/api/settings/test-gemini")
def test_gemini_connection(payload: Dict[str, str]):
    """Test Gemini API key with a fast ping."""
    key = payload.get("gemini_api_key") or os.getenv("GEMINI_API_KEY", GEMINI_API_KEY)
    if not key:
        return {"success": False, "message": "Gemini API key is not provided."}

    try:
        from google import genai
        client = genai.Client(api_key=key)
        response = client.models.generate_content(
            model=os.getenv("GEMINI_MODEL", GEMINI_MODEL),
            contents="Say 'OK' if you can read this.",
        )
        return {"success": True, "message": f"Connected to Gemini API successfully! Model response: {response.text.strip()}"}
    except Exception as e:
        return {"success": False, "message": f"Gemini API connection error: {str(e)}"}


@app.post("/api/sync")
async def sync_zotero(
    req: SyncRequest = SyncRequest(),
    current_user: Optional[Dict[str, Any]] = Depends(get_current_user) if get_current_user else None,
    db: Session = Depends(get_db)
):
    """Triggers a sync with Zotero using credentials from request, user profile, or environment."""
    lib_id = (req.library_id or "").strip()
    api_key = (req.api_key or "").strip()
    lib_type = (req.library_type or "user").strip()

    # Check authenticated user's profile if credentials not in payload
    if (not lib_id or not api_key) and current_user and SUPABASE_URL and SUPABASE_KEY:
        try:
            user_id = current_user.get("id")
            async with httpx.AsyncClient(timeout=4.0) as client:
                resp = await client.get(
                    f"{SUPABASE_URL.rstrip('/')}/rest/v1/profiles",
                    params={"id": f"eq.{user_id}", "select": "zotero_user_id,zotero_api_key"},
                    headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}
                )
                if resp.status_code == 200 and resp.json():
                    p = resp.json()[0]
                    if not lib_id and p.get("zotero_user_id"):
                        lib_id = p.get("zotero_user_id")
                    if not api_key and p.get("zotero_api_key"):
                        api_key = p.get("zotero_api_key")
        except Exception as e:
            logger.warning(f"Error fetching profile credentials for sync: {e}")

    # Fallback to server environment variables
    if not lib_id:
        lib_id = os.getenv("ZOTERO_LIBRARY_ID", ZOTERO_LIBRARY_ID or "")
    if not api_key:
        api_key = os.getenv("ZOTERO_API_KEY", ZOTERO_API_KEY or "")

    service = ZoteroSyncService(
        library_id=lib_id,
        library_type=lib_type,
        api_key=api_key
    )

    if not service.client:
        raise HTTPException(
            status_code=400,
            detail="Zotero credentials missing. Please enter your Zotero User ID and API Key to sync."
        )

    user_id = str(current_user["id"]) if current_user and current_user.get("id") else None
    result = service.sync_library(db=db, limit=req.limit or 25, user_id=user_id)
    return result


@app.get("/api/papers")
def list_papers(
    status: Optional[str] = Query(None, description="Filter by status: Pending, Processing, Ready, Failed"),
    search: Optional[str] = Query(None, description="Search term for title or author"),
    has_pdf: Optional[bool] = Query(None, description="Filter papers having PDF"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    scope: Optional[str] = Query(None, description="Scope filter: 'user', 'demo', or 'all'"),
    current_user: Optional[Dict[str, Any]] = Depends(get_current_user) if get_current_user else None,
    db: Session = Depends(get_db)
):
    """Returns list of ingested papers scoped to authenticated user."""
    query = db.query(Paper)

    if current_user and current_user.get("id"):
        user_id = str(current_user["id"])
        query = query.filter(Paper.user_id == user_id)
    elif scope in ("demo", "all"):
        query = query.filter(or_(Paper.user_id == None, Paper.user_id == "demo"))
    else:
        # Unauthenticated: do not expose random seed papers
        return {
            "total": 0,
            "ready_count": 0,
            "total_audio_minutes": 0,
            "papers": [],
            "authenticated": False,
            "message": "Sign in to view your personalized ingested papers."
        }

    if status:
        query = query.filter(Paper.status == status)

    if has_pdf is not None:
        query = query.filter(Paper.has_pdf == has_pdf)

    if search:
        search_filter = f"%{search.strip()}%"
        query = query.filter(
            or_(
                Paper.title.ilike(search_filter),
                Paper.authors.ilike(search_filter),
                Paper.abstract.ilike(search_filter),
            )
        )

    total_count = query.count()
    papers = query.order_by(desc(Paper.created_at)).offset(offset).limit(limit).all()

    # Fast SQL aggregate metrics (sub-millisecond)
    ready_count = query.filter(Paper.status == "Ready").count()
    total_audio_seconds = query.filter(Paper.status == "Ready").with_entities(func.coalesce(func.sum(Paper.audio_duration), 0.0)).scalar() or 0.0

    paper_list = []
    for p in papers:
        # include_full_text=False for ultra-fast, lightweight listing payloads (<3KB vs 300KB)
        p_dict = p.to_dict(include_full_text=False)
        if p.id in ACTIVE_SYNTHESIS_PROGRESS:
            p_dict["synthesis_progress"] = ACTIVE_SYNTHESIS_PROGRESS[p.id]
        paper_list.append(p_dict)

    return {
        "total": total_count,
        "ready_count": ready_count,
        "total_audio_minutes": round(total_audio_seconds / 60.0, 1),
        "papers": paper_list,
        "authenticated": True
    }


@app.get("/api/papers/{paper_id}")
def get_paper(paper_id: int, db: Session = Depends(get_db)):
    """Retrieve detailed record for a specific paper."""
    paper = db.query(Paper).filter(Paper.id == paper_id).first()
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")

    # Auto-extract full verbatim text on-demand in milliseconds if not yet cached
    if (not paper.full_text or not paper.full_text.strip()):
        if paper.pdf_path and os.path.exists(paper.pdf_path):
            try:
                verbatim_text, _ = PDFProcessor.extract_verbatim_text(paper.pdf_path)
                paper.full_text = verbatim_text
                db.commit()
                db.refresh(paper)
            except Exception as e:
                logger.warning(f"Error auto-extracting text on get_paper: {e}")
        elif paper.abstract:
            paper.full_text = paper.abstract
            db.commit()
            db.refresh(paper)

    d = paper.to_dict()
    d["chapters"] = extract_document_chapters(paper)
    if paper.id in ACTIVE_SYNTHESIS_PROGRESS:
        d["synthesis_progress"] = ACTIVE_SYNTHESIS_PROGRESS[paper.id]
    return d


@app.get("/api/papers/{paper_id}/chapters")
def get_paper_chapters(paper_id: int, db: Session = Depends(get_db)):
    """Extracts navigation chapters and timestamps for seeking specific parts of the audio."""
    paper = db.query(Paper).filter(Paper.id == paper_id).first()
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")
    return extract_document_chapters(paper)


@app.post("/api/papers/{paper_id}/extract-text")
def extract_paper_text(paper_id: int, db: Session = Depends(get_db)):
    """Instantly extracts full verbatim text from paper's PDF in milliseconds without audio synthesis."""
    paper = db.query(Paper).filter(Paper.id == paper_id).first()
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")

    if paper.pdf_path and os.path.exists(paper.pdf_path):
        verbatim_text, total_pages = PDFProcessor.extract_verbatim_text(paper.pdf_path)
        paper.full_text = verbatim_text
        db.commit()
        db.refresh(paper)
        return {
            "success": True,
            "message": f"Extracted {len(verbatim_text)} characters across {total_pages} pages.",
            "full_text": verbatim_text,
            "total_pages": total_pages,
            "words": len(verbatim_text.split())
        }
    elif paper.abstract:
        paper.full_text = paper.abstract
        db.commit()
        db.refresh(paper)
        return {
            "success": True,
            "message": "Used abstract as full text (no attached PDF).",
            "full_text": paper.abstract,
            "total_pages": 1,
            "words": len(paper.abstract.split())
        }
    else:
        raise HTTPException(status_code=400, detail="No PDF file or abstract available for text extraction.")


@app.post("/api/papers/{paper_id}/chat")
def chat_with_paper_endpoint(paper_id: int, payload: PaperChatRequest, db: Session = Depends(get_db)):
    """Dynamic conversational AI mentor to ask questions and chat with a research paper."""
    paper = db.query(Paper).filter(Paper.id == paper_id).first()
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")

    summarizer = GeminiSummarizer(api_key=GEMINI_API_KEY, model=GEMINI_MODEL)
    breakdown = {
        "problem": paper.summary_problem or "",
        "methodology": paper.summary_methodology or "",
        "results": paper.summary_results or "",
        "limitations": paper.summary_limitations or ""
    }

    # Extract figures and diagrams context if attached PDF exists
    figures = []
    if paper.pdf_path and os.path.exists(paper.pdf_path):
        try:
            figures = PDFProcessor.extract_figures(paper.pdf_path, paper.id)
        except Exception as e:
            logger.warning(f"Error extracting figures for chat context: {e}")

    reply = summarizer.chat_with_paper(
        title=paper.title or "Research Paper",
        abstract=paper.abstract or "",
        full_text=paper.full_text or "",
        breakdown_sections=breakdown,
        user_question=payload.message,
        history=payload.history or [],
        figures=figures
    )

    # Persist chat history directly into database
    try:
        existing_chat = json.loads(paper.chat_history_json or "[]")
    except Exception:
        existing_chat = []
    existing_chat.append({"role": "user", "content": payload.message, "timestamp": datetime.utcnow().isoformat()})
    existing_chat.append({"role": "assistant", "content": reply, "timestamp": datetime.utcnow().isoformat()})
    paper.chat_history_json = json.dumps(existing_chat[-60:])
    db.commit()

    return {"reply": reply, "paper_title": paper.title, "figures_available": len(figures)}


@app.get("/api/papers/{paper_id}/chat")
def get_paper_chat_history(paper_id: int, db: Session = Depends(get_db)):
    """Retrieve saved conversational AI mentor chat history directly from database."""
    paper = db.query(Paper).filter(Paper.id == paper_id).first()
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")
    try:
        history = json.loads(paper.chat_history_json or "[]")
    except Exception:
        history = []
    return {"paper_id": paper_id, "history": history}


@app.delete("/api/papers/{paper_id}/chat")
def clear_paper_chat_endpoint(paper_id: int, db: Session = Depends(get_db)):
    """Clears server-side recorded chat session for a paper in database."""
    paper = db.query(Paper).filter(Paper.id == paper_id).first()
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")
    paper.chat_history_json = "[]"
    db.commit()
    return {"status": "cleared", "paper_id": paper_id}


def _get_notes_file(paper_id: int) -> Path:
    import tempfile
    if IS_SERVERLESS or not is_writable:
        notes_dir = Path("/tmp/notes") if (os.name != "nt" or Path("/tmp").exists()) else Path(tempfile.gettempdir()) / "zam_notes"
    else:
        notes_dir = BASE_DIR / "data" / "notes"
    try:
        notes_dir.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
    return notes_dir / f"notes_{paper_id}.json"


def _load_paper_notes(paper_id: int, db: Optional[Session] = None) -> List[Dict[str, Any]]:
    if db:
        try:
            paper = db.query(Paper).filter(Paper.id == paper_id).first()
            if paper and paper.notes_json:
                db_notes = json.loads(paper.notes_json)
                if db_notes:
                    return db_notes
        except Exception as e:
            logger.warning(f"Could not load notes from database: {e}")
    f = _get_notes_file(paper_id)
    if f.exists():
        try:
            return json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            return []
    return []


def _save_paper_notes(paper_id: int, notes: List[Dict[str, Any]], db: Optional[Session] = None):
    if db:
        try:
            paper = db.query(Paper).filter(Paper.id == paper_id).first()
            if paper:
                paper.notes_json = json.dumps(notes)
                db.commit()
        except Exception as e:
            logger.warning(f"Could not persist notes to database for paper {paper_id}: {e}")
    f = _get_notes_file(paper_id)
    try:
        f.write_text(json.dumps(notes, indent=2), encoding="utf-8")
    except Exception as e:
        logger.warning(f"Could not persist notes to {f}: {e}")


@app.get("/api/papers/{paper_id}/notes")
def get_paper_notes(paper_id: int, db: Session = Depends(get_db)):
    """Retrieve saved highlights and professional notes for a research paper from database."""
    notes = _load_paper_notes(paper_id, db=db)
    return {"paper_id": paper_id, "notes": notes, "total": len(notes)}


@app.post("/api/papers/{paper_id}/notes")
def save_paper_note(paper_id: int, payload: PaperNoteRequest, db: Session = Depends(get_db)):
    """Save or update a highlighted passage and professional note directly into database."""
    notes = _load_paper_notes(paper_id, db=db)
    note_id = payload.id or f"note_{int(datetime.utcnow().timestamp() * 1000)}"
    new_note = {
        "id": note_id,
        "title": payload.title or "Professional Note",
        "content": payload.content,
        "quote": payload.quote or "",
        "category": payload.category or "Methodology",
        "color": payload.color or "yellow",
        "created_at": payload.created_at or datetime.utcnow().isoformat()
    }
    existing_idx = next((i for i, n in enumerate(notes) if n.get("id") == note_id), None)
    if existing_idx is not None:
        notes[existing_idx] = new_note
    else:
        notes.insert(0, new_note)
    _save_paper_notes(paper_id, notes, db=db)
    return {"success": True, "note": new_note, "total": len(notes)}


@app.delete("/api/papers/{paper_id}/notes/{note_id}")
def delete_paper_note(paper_id: int, note_id: str, db: Session = Depends(get_db)):
    """Delete a professional research note from database."""
    notes = _load_paper_notes(paper_id, db=db)
    notes = [n for n in notes if n.get("id") != note_id]
    _save_paper_notes(paper_id, notes, db=db)
    return {"success": True, "deleted_id": note_id, "total": len(notes)}


@app.get("/api/papers/{paper_id}/pdf")
def download_paper_pdf(paper_id: int, db: Session = Depends(get_db)):
    """Directly download the original paper PDF file to the researcher's computer."""
    paper = db.query(Paper).filter(Paper.id == paper_id).first()
    if not paper or not paper.pdf_path:
        raise HTTPException(status_code=404, detail="PDF not attached to this paper")

    pdf_file = Path(paper.pdf_path)
    if not pdf_file.exists():
        alt1 = PDFS_DIR / pdf_file.name
        alt2 = Path("/tmp/pdfs") / pdf_file.name
        if alt1.exists():
            pdf_file = alt1
        elif alt2.exists():
            pdf_file = alt2
        else:
            raise HTTPException(status_code=404, detail="PDF file not found on disk")

    safe_title = "".join(c for c in (paper.title or "research_paper") if c.isalnum() or c in " _-")[:60].strip()
    return FileResponse(
        path=str(pdf_file),
        media_type="application/pdf",
        filename=f"{safe_title}.pdf"
    )


@app.post("/api/process/{item_key_or_id}")
async def process_paper(
    item_key_or_id: str,
    req: ProcessRequest = ProcessRequest(),
    background_tasks: BackgroundTasks = None,
    db: Session = Depends(get_db)
):
    """
    Triggers pipeline for a paper:
    - mode="summary": Extract -> Gemini 4-part mentor briefing -> Edge-TTS Audio -> Update DB
    - mode="full_paper": Extract -> Clean full paper text -> Edge-TTS Full Audio -> Update DB
    Accepts either database paper id or Zotero item key.
    """
    paper = None
    if item_key_or_id.isdigit():
        paper = db.query(Paper).filter(Paper.id == int(item_key_or_id)).first()

    if not paper:
        paper = db.query(Paper).filter(Paper.zotero_item_key == item_key_or_id).first()

    if not paper:
        raise HTTPException(status_code=404, detail=f"Paper '{item_key_or_id}' not found.")

    target_mode = req.mode or "summary"
    paper.status = "Processing"
    paper.error_message = None
    db.commit()

    # Launch processing in background task to avoid client timeouts on long full papers
    async def run_pipeline():
        try:
            from backend.database import SessionLocal
        except ImportError:
            from database import SessionLocal
        bg_db = SessionLocal()
        try:
            await execute_processing_pipeline(
                paper_id=paper.id,
                mode=target_mode,
                voice=req.voice,
                gemini_key=req.gemini_api_key,
                gemini_model=req.gemini_model,
                scope=req.scope or "article",
                db=bg_db
            )
        except Exception as err:
            logger.error(f"Background pipeline failed for paper {paper.id}: {err}", exc_info=True)
        finally:
            bg_db.close()

    if IS_SERVERLESS:
        # On Vercel / serverless functions, background tasks get frozen immediately when HTTP response returns!
        # Run directly while the execution context is alive to prevent synthesis stalling:
        logger.info(f"Serverless environment detected (Vercel): executing pipeline synchronously for paper {paper.id}...")
        try:
            await execute_processing_pipeline(
                paper_id=paper.id,
                mode=target_mode,
                voice=req.voice,
                gemini_key=req.gemini_api_key,
                gemini_model=req.gemini_model,
                scope=req.scope or "article",
                db=db
            )
            db.refresh(paper)
            return {
                "success": True,
                "message": f"Processing ({target_mode}) completed successfully.",
                "paper": paper.to_dict()
            }
        except Exception as e:
            logger.error(f"Serverless pipeline failed for paper {paper.id}: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"Synthesis failed: {str(e)}")
    else:
        asyncio.create_task(run_pipeline())
        return {
            "success": True,
            "message": f"Processing ({target_mode}) started in background.",
            "paper": paper.to_dict()
        }


@app.post("/api/process-batch")
async def process_batch_papers(
    req: ProcessRequest = ProcessRequest(),
    background_tasks: BackgroundTasks = None,
    db: Session = Depends(get_db)
):
    """Processes all pending papers sequentially in the background."""
    pending_papers = db.query(Paper).filter(Paper.status == "Pending").all()
    if not pending_papers:
        return {"success": True, "message": "No pending papers to process.", "count": 0}

    target_mode = req.mode or "summary"
    # Queue background execution
    for paper in pending_papers:
        await execute_processing_pipeline(
            paper_id=paper.id,
            mode=target_mode,
            voice=req.voice,
            gemini_key=req.gemini_api_key,
            gemini_model=req.gemini_model,
            db=db
        )

    return {
        "success": True,
        "message": f"Triggered processing for {len(pending_papers)} pending papers in '{target_mode}' mode.",
        "count": len(pending_papers)
    }


@app.post("/api/papers/{paper_id}/switch-mode")
def switch_paper_mode(paper_id: int, req: SwitchModeRequest, db: Session = Depends(get_db)):
    """Switches the active audio track for a paper between 'summary' and 'full_paper'."""
    paper = db.query(Paper).filter(Paper.id == paper_id).first()
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")

    target_mode = (req.mode or "summary").lower()
    if target_mode not in ["summary", "full_paper"]:
        raise HTTPException(status_code=400, detail="Invalid mode. Must be 'summary' or 'full_paper'.")

    if target_mode == "summary":
        has_summary = bool(paper.summary_audio_path or (paper.audio_path and paper.audio_mode == "summary"))
        if not has_summary:
            return {
                "success": False,
                "needs_generation": True,
                "message": "Summary audio briefing has not been generated yet for this paper."
            }
        paper.audio_mode = "summary"
        if paper.summary_audio_path:
            paper.audio_path = paper.summary_audio_path
            paper.audio_duration = paper.summary_audio_duration or 0.0
        db.commit()
        return {"success": True, "paper": paper.to_dict()}

    elif target_mode == "full_paper":
        has_full = bool(paper.full_audio_path or (paper.audio_path and paper.audio_mode == "full_paper"))
        if not has_full:
            return {
                "success": False,
                "needs_generation": True,
                "message": "Full paper audio reading has not been generated yet for this paper."
            }
        paper.audio_mode = "full_paper"
        if paper.full_audio_path:
            paper.audio_path = paper.full_audio_path
            paper.audio_duration = paper.full_audio_duration or 0.0
        db.commit()
        return {"success": True, "paper": paper.to_dict()}


@app.post("/api/upload")
async def upload_pdf(
    file: UploadFile = File(...),
    title: Optional[str] = Form(None),
    authors: Optional[str] = Form(None),
    auto_process: bool = Form(False),
    mode: Optional[str] = Form("summary"),
    voice: Optional[str] = Form(None),
    current_user: Optional[Dict[str, Any]] = Depends(get_current_user) if get_current_user else None,
    db: Session = Depends(get_db)
):
    """Directly upload a research PDF file without requiring Zotero setup."""
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported.")

    import uuid
    file_id = f"upload_{uuid.uuid4().hex[:8]}"
    saved_filename = f"{file_id}_{file.filename}"
    target_path = PDFS_DIR / saved_filename

    with open(target_path, "wb") as buffer:
        while chunk := await file.read(1024 * 1024):
            buffer.write(chunk)

    # Inspect PDF metadata or first page to infer title if not provided
    doc_title = title
    doc_authors = authors or "Uploaded Researcher"
    abstract_preview = ""

    try:
        if fitz is not None:
            doc = fitz.open(target_path)
            meta = doc.metadata or {}
            if not doc_title:
                doc_title = meta.get("title") or file.filename.replace(".pdf", "").replace("_", " ").title()
            if not authors and meta.get("author"):
                doc_authors = meta.get("author")

            # Grab first 800 chars for preview
            if len(doc) > 0:
                first_page_text = doc[0].get_text("text")
                abstract_preview = first_page_text[:1200].strip()
            doc.close()
        elif pypdf is not None:
            reader = pypdf.PdfReader(target_path)
            meta = reader.metadata
            if not doc_title:
                doc_title = getattr(meta, 'title', None) or file.filename.replace(".pdf", "").replace("_", " ").title()
            if not authors and getattr(meta, 'author', None):
                doc_authors = getattr(meta, 'author', None)
            if len(reader.pages) > 0:
                first_page_text = reader.pages[0].extract_text() or ""
                abstract_preview = first_page_text[:1200].strip()
    except Exception as e:
        logger.warning(f"Could not read PDF metadata: {e}")
        if not doc_title:
            doc_title = file.filename.replace(".pdf", "").replace("_", " ").title()

    # Extract complete verbatim text immediately upon upload (takes ~0.1-0.2s)
    full_verbatim_text = ""
    try:
        full_verbatim_text, _ = PDFProcessor.extract_verbatim_text(target_path)
    except Exception as e:
        logger.warning(f"Could not extract verbatim text upon upload: {e}")

    initial_status = "Processing" if auto_process else "Pending"
    user_id = str(current_user["id"]) if current_user and current_user.get("id") else None
    paper = Paper(
        user_id=user_id,
        zotero_item_key=file_id,
        title=doc_title,
        authors=doc_authors,
        abstract=abstract_preview,
        full_text=full_verbatim_text or abstract_preview,
        pdf_path=str(target_path),
        has_pdf=True,
        status=initial_status,
        publication_year=str(import_year := 2026)
    )
    db.add(paper)
    db.commit()
    db.refresh(paper)

    # Launch processing asynchronously in background to ensure upload responds in milliseconds
    if auto_process:
        asyncio.create_task(
            execute_processing_pipeline(
                paper_id=paper.id,
                mode=mode or "summary",
                voice=voice or DEFAULT_TTS_VOICE
            )
        )

    return {
        "success": True,
        "message": f"Successfully uploaded '{doc_title}'.",
        "paper": paper.to_dict()
    }


@app.post("/api/sample-papers")
async def load_sample_papers(db: Session = Depends(get_db)):
    """Populates the database with benchmark AI research papers for immediate out-of-the-box demoing."""
    samples = [
        {
            "zotero_item_key": "ATTN_2017",
            "title": "Attention Is All You Need",
            "authors": "Ashish Vaswani, Noam Shazeer, Niki Parmar, Jakob Uszkoreit, Llion Jones, Aidan N. Gomez, Łukasz Kaiser, Illia Polosukhin",
            "publication_year": "2017",
            "journal": "Advances in Neural Information Processing Systems (NeurIPS)",
            "abstract": "The dominant sequence transduction models are based on complex recurrent or convolutional neural networks that include an encoder and a decoder. The best performing models also connect the encoder and decoder through an attention mechanism. We propose a new simple network architecture, the Transformer, based solely on attention mechanisms, dispensing with recurrence and convolutions entirely. Experiments on two machine translation tasks show these models to be superior in quality while being more parallelizable and requiring significantly less time to train."
        },
        {
            "zotero_item_key": "LORA_2021",
            "title": "LoRA: Low-Rank Adaptation of Large Language Models",
            "authors": "Edward J. Hu, Yelong Shen, Phillip Wallis, Zeyuan Allen-Zhu, Yuanzhi Li, Shean Wang, Lu Wang, Weizhu Chen",
            "publication_year": "2021",
            "journal": "International Conference on Learning Representations (ICLR)",
            "abstract": "An important paradigm of natural language processing consists of large-scale pre-training on general domain data and adaptation to specific tasks. As we pre-train larger models, full fine-tuning becomes increasingly infeasible. We propose Low-Rank Adaptation (LoRA), which freezes the pre-trained model weights and injects trainable rank decomposition matrices into each layer of the Transformer architecture, greatly reducing the number of trainable parameters for downstream tasks. Compared to fine-tuning of GPT-3 175B with Adam, LoRA can reduce the number of trainable parameters by 10,000 times and the GPU memory requirement by 3 times."
        },
        {
            "zotero_item_key": "RAG_2020",
            "title": "Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks",
            "authors": "Patrick Lewis, Ethan Perez, Aleksandra Piktus, Fabio Petroni, Vladimir Karpukhin, Naman Goyal, Heinrich Küttler, Mike Lewis, Wen-tau Yih, Tim Rocktäschel, Sebastian Riedel, Douwe Kiela",
            "publication_year": "2020",
            "journal": "Advances in Neural Information Processing Systems (NeurIPS)",
            "abstract": "Large pre-trained language models have been shown to store factual knowledge in their parameters, and achieve state-of-the-art results when fine-tuned on downstream NLP tasks. However, their ability to precisely access and manipulate knowledge is still limited. We explore a general-purpose fine-tuning recipe for retrieval-augmented generation (RAG)—models which combine pre-trained parametric and non-parametric memory for language generation. We introduce RAG models where the parametric memory is a pre-trained seq2seq model and the non-parametric memory is a dense vector index of Wikipedia, accessed with a pre-trained neural retriever."
        },
        {
            "zotero_item_key": "DPO_2023",
            "title": "Direct Preference Optimization: Your Language Model is Secretly a Reward Model",
            "authors": "Rafael Rafailov, Archit Sharma, Eric Mitchell, Stefano Ermon, Christopher D. Manning, Chelsea Finn",
            "publication_year": "2023",
            "journal": "Advances in Neural Information Processing Systems (NeurIPS)",
            "abstract": "While large-scale language models can learn broad general knowledge, controlling their behavior via human feedback is crucial. Existing techniques use Reinforcement Learning from Human Feedback (RLHF), which fits a reward model to a dataset of human preferences and then optimizes a policy via RL algorithms like PPO. However, RLHF is complex and unstable. We propose Direct Preference Optimization (DPO), a mathematically principled algorithm that optimizes policy directly from preference data without training a separate reward model or sampling from the LM during fine-tuning."
        }
    ]

    added = 0
    for s in samples:
        existing = db.query(Paper).filter(Paper.zotero_item_key == s["zotero_item_key"]).first()
        if not existing:
            p = Paper(
                zotero_item_key=s["zotero_item_key"],
                title=s["title"],
                authors=s["authors"],
                publication_year=s["publication_year"],
                journal=s["journal"],
                abstract=s["abstract"],
                status="Pending",
                has_pdf=False
            )
            db.add(p)
            added += 1

    db.commit()
    return {
        "success": True,
        "message": f"Loaded {added} benchmark research papers into your library.",
        "total_samples": len(samples)
    }


@app.delete("/api/papers/{paper_id}")
def delete_paper(paper_id: int, db: Session = Depends(get_db)):
    """Delete a paper record and its associated audio/PDF files."""
    paper = db.query(Paper).filter(Paper.id == paper_id).first()
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")

    # Delete audio files if exist
    audio_paths_to_remove = set(filter(None, [paper.audio_path, paper.summary_audio_path, paper.full_audio_path]))
    for a_path in audio_paths_to_remove:
        filename = a_path.split("/")[-1]
        audio_file = AUDIO_DIR / filename
        if audio_file.exists():
            try:
                audio_file.unlink()
            except Exception as e:
                logger.warning(f"Could not remove audio file {audio_file}: {e}")

    # Delete PDF file if it was a local download/upload
    if paper.pdf_path and os.path.exists(paper.pdf_path):
        try:
            Path(paper.pdf_path).unlink()
        except Exception as e:
            logger.warning(f"Could not remove PDF file {paper.pdf_path}: {e}")

    db.delete(paper)
    db.commit()
    return {"success": True, "message": f"Paper '{paper.title}' deleted."}


@app.get("/api/audio/{filename}")
async def stream_audio(filename: str, db: Session = Depends(get_db)):
    """Streams generated MP3 audio files with support for HTTP Range requests, instant DB blob recovery, and on-demand synthesis."""
    audio_path = AUDIO_DIR / filename

    # 1. If audio file already exists on disk, stream immediately
    if audio_path.exists() and audio_path.stat().st_size > 0:
        return FileResponse(
            path=str(audio_path),
            media_type="audio/mpeg",
            filename=filename,
            headers={"Accept-Ranges": "bytes"}
        )

    # 2. File not on disk (system launch, container reboot, or cleared temp dir).
    # Check if the audio blob is safely preserved in the database!
    import re
    match = re.match(r"^paper_(\d+)(?:_(full))?", filename)
    if match:
        paper_id = int(match.group(1))
        is_full = bool(match.group(2))

        # Query the exact audio blob
        blob_column = Paper.full_audio_blob if is_full else Paper.summary_audio_blob
        blob_data = db.query(blob_column).filter(Paper.id == paper_id).scalar()

        if blob_data and len(blob_data) > 0:
            logger.info(f"Instant audio restore: Serving paper {paper_id} ({len(blob_data)} bytes) directly from database blob.")
            try:
                audio_path.parent.mkdir(parents=True, exist_ok=True)
                audio_path.write_bytes(blob_data)
                return FileResponse(
                    path=str(audio_path),
                    media_type="audio/mpeg",
                    filename=filename,
                    headers={"Accept-Ranges": "bytes"}
                )
            except Exception as disk_err:
                logger.warning(f"Could not cache restored audio blob to disk: {disk_err}. Streaming directly from database blob.")
                return Response(
                    content=blob_data,
                    media_type="audio/mpeg",
                    headers={
                        "Content-Disposition": f'inline; filename="{filename}"',
                        "Accept-Ranges": "bytes"
                    }
                )

        # 3. Only if blob is NOT in database, fall back to on-demand synthesis
        paper = db.query(Paper).filter(Paper.id == paper_id).first()
        if paper:
            selected_voice = paper.voice_used or DEFAULT_TTS_VOICE
            try:
                if is_full:
                    text_to_speak = paper.full_text or paper.summary_text or paper.abstract
                    if text_to_speak and text_to_speak.strip():
                        cleaned = AudioSynthesizer.prepare_verbatim_for_speech(text_to_speak)
                        synth_path, dur = await AudioSynthesizer.synthesize_long_text_async(
                            text=cleaned,
                            output_filename=filename,
                            voice=selected_voice
                        )
                        paper.full_audio_duration = dur
                        if synth_path and os.path.exists(synth_path):
                            paper.full_audio_blob = Path(synth_path).read_bytes()
                        db.commit()
                else:
                    text_to_speak = paper.summary_text
                    if not text_to_speak or not text_to_speak.strip():
                        if paper.summary_problem:
                            text_to_speak = (
                                f"## 1. The Core Problem\n{paper.summary_problem}\n\n"
                                f"## 2. Methodology\n{paper.summary_methodology or ''}\n\n"
                                f"## 3. Key Results\n{paper.summary_results or ''}\n\n"
                                f"## 4. Limitations\n{paper.summary_limitations or ''}"
                            )
                        else:
                            text_to_speak = paper.abstract or paper.title
                    if text_to_speak and text_to_speak.strip():
                        synth_path, dur = await AudioSynthesizer.synthesize_audio_async(
                            text=text_to_speak,
                            output_filename=filename,
                            voice=selected_voice
                        )
                        paper.summary_audio_duration = dur
                        if synth_path and os.path.exists(synth_path):
                            paper.summary_audio_blob = Path(synth_path).read_bytes()
                        db.commit()
            except Exception as e:
                logger.warning(f"On-demand audio recovery failed: {e}")

    if not audio_path.exists():
        raise HTTPException(status_code=404, detail=f"Audio file '{filename}' not found.")

    return FileResponse(
        path=str(audio_path),
        media_type="audio/mpeg",
        filename=filename,
        headers={"Accept-Ranges": "bytes"}
    )


@app.post("/api/papers/{paper_id}/change-voice")
async def change_paper_voice(paper_id: int, payload: VoiceChangeRequest, db: Session = Depends(get_db)):
    """Re-synthesizes paper audio with a newly selected accent/voice and updates the database blob."""
    paper = db.query(Paper).filter(Paper.id == paper_id).first()
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")

    selected_voice = payload.voice or DEFAULT_TTS_VOICE
    mode = payload.mode or "summary"

    if mode == "full_paper":
        verbatim_text = paper.full_text
        if not verbatim_text or not verbatim_text.strip():
            if paper.pdf_path and os.path.exists(paper.pdf_path):
                verbatim_text = PDFProcessor.extract_full_text(paper.pdf_path)
                paper.full_text = verbatim_text
            else:
                verbatim_text = paper.abstract or paper.title

        cleaned_speech = AudioSynthesizer.prepare_verbatim_for_speech(verbatim_text)
        audio_filename = f"paper_{paper.id}_full_{paper.zotero_item_key or 'direct'}.mp3"
        out_path, duration = await AudioSynthesizer.synthesize_long_text_async(
            text=cleaned_speech,
            output_filename=audio_filename,
            voice=selected_voice
        )
        if out_path and os.path.exists(out_path):
            file_size = os.path.getsize(out_path)
            if file_size < 25 * 1024 * 1024:
                try:
                    paper.full_audio_blob = Path(out_path).read_bytes()
                except Exception as b_err:
                    logger.warning(f"Failed to update full_audio_blob in database: {b_err}")
        paper.full_audio_path = f"/api/audio/{audio_filename}"
        paper.full_audio_duration = duration
        paper.audio_path = paper.full_audio_path
        paper.audio_duration = duration
        paper.audio_mode = "full_paper"
    else:
        briefing_script = paper.summary_text
        if not briefing_script or not briefing_script.strip():
            briefing_script = (
                f"## 1. The Core Problem\n{paper.summary_problem or paper.abstract or paper.title}\n\n"
                f"## 2. Methodology\n{paper.summary_methodology or 'Not specified.'}\n\n"
                f"## 3. Key Results\n{paper.summary_results or 'Not specified.'}\n\n"
                f"## 4. Limitations\n{paper.summary_limitations or 'Not specified.'}"
            )

        audio_filename = f"paper_{paper.id}_{paper.zotero_item_key or 'direct'}.mp3"
        out_path, duration = await AudioSynthesizer.synthesize_audio_async(
            text=briefing_script,
            output_filename=audio_filename,
            voice=selected_voice
        )
        if out_path and os.path.exists(out_path):
            try:
                paper.summary_audio_blob = Path(out_path).read_bytes()
            except Exception as b_err:
                logger.warning(f"Failed to update summary_audio_blob in database: {b_err}")
        paper.summary_audio_path = f"/api/audio/{audio_filename}"
        paper.summary_audio_duration = duration
        paper.audio_path = paper.summary_audio_path
        paper.audio_duration = duration
        paper.audio_mode = "summary"

    paper.voice_used = selected_voice
    paper.status = "Ready"
    paper.error_message = None
    db.commit()
    db.refresh(paper)

    return {
        "success": True,
        "message": f"Synthesized with voice '{selected_voice}'.",
        "audio_path": paper.audio_path,
        "audio_duration": paper.audio_duration,
        "voice_used": paper.voice_used,
        "audio_mode": paper.audio_mode
    }


@app.get("/api/papers/{paper_id}/figures")
def get_paper_figures(paper_id: int, db: Session = Depends(get_db)):
    """Extracts and returns list of diagrams, figures, and charts from the paper's PDF."""
    paper = db.query(Paper).filter(Paper.id == paper_id).first()
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")

    if not paper.pdf_path or not os.path.exists(paper.pdf_path):
        return {"figures": [], "count": 0, "has_pdf": False}

    figures = PDFProcessor.extract_figures(paper.pdf_path, paper.id)
    return {
        "figures": figures,
        "count": len(figures),
        "has_pdf": True
    }


@app.get("/api/papers/{paper_id}/pdf")
def stream_paper_pdf(paper_id: int, db: Session = Depends(get_db)):
    """Streams paper PDF by paper ID with inline disposition."""
    paper = db.query(Paper).filter(Paper.id == paper_id).first()
    if not paper or not paper.pdf_path or not os.path.exists(paper.pdf_path):
        raise HTTPException(status_code=404, detail="Paper PDF not found")
    filename = os.path.basename(paper.pdf_path)
    return FileResponse(
        path=paper.pdf_path,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f"inline; filename=\"{filename}\"",
            "Accept-Ranges": "bytes"
        }
    )


@app.get("/api/pdf/{filename}")
def stream_pdf(filename: str):
    """Streams PDF files with inline disposition for seamless iframe and tab viewing."""
    pdf_path = PDFS_DIR / filename
    if not pdf_path.exists():
        raise HTTPException(status_code=404, detail=f"PDF file '{filename}' not found.")

    return FileResponse(
        path=str(pdf_path),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f"inline; filename=\"{filename}\"",
            "Accept-Ranges": "bytes"
        }
    )


@app.post("/api/conferences/search")
def search_conferences(payload: ConferenceSearchRequest):
    """Intelligent conference and academic event scout for PhD researchers."""
    scout = ConferenceScoutService(api_key=GEMINI_API_KEY, model=GEMINI_MODEL)
    return scout.search(
        query=payload.query or "",
        year=payload.year,
        doctoral_only=bool(payload.doctoral_only),
        grants_only=bool(payload.grants_only),
        region=payload.region,
        upcoming_only=payload.upcoming_only if payload.upcoming_only is not None else True
    )


@app.get("/api/conferences/featured")
def get_featured_conferences():
    """Returns top curated academic conferences with active doctoral consortiums."""
    scout = ConferenceScoutService(api_key=GEMINI_API_KEY, model=GEMINI_MODEL)
    return scout.search(query="", upcoming_only=True)


_CONFERENCE_WATCHLIST: List[dict] = []


@app.post("/api/conferences/watchlist")
def add_to_conference_watchlist(payload: ConferenceWatchlistRequest):
    """Add a conference to researcher's monitored watchlist."""
    item = payload.dict()
    item["id"] = len(_CONFERENCE_WATCHLIST) + 1
    existing = [x for x in _CONFERENCE_WATCHLIST if x.get("acronym", "").upper() == item["acronym"].upper()]
    if not existing:
        _CONFERENCE_WATCHLIST.append(item)
    else:
        item = existing[0]
    return {"status": "success", "item": item, "total": len(_CONFERENCE_WATCHLIST)}


@app.get("/api/conferences/watchlist")
def get_conference_watchlist():
    """Retrieve researcher's monitored conference watchlist."""
    return {
        "status": "success",
        "total": len(_CONFERENCE_WATCHLIST),
        "items": _CONFERENCE_WATCHLIST
    }


@app.delete("/api/conferences/watchlist/{acronym}")
def remove_from_conference_watchlist(acronym: str):
    """Remove a conference from researcher's watchlist."""
    global _CONFERENCE_WATCHLIST
    _CONFERENCE_WATCHLIST = [x for x in _CONFERENCE_WATCHLIST if x.get("acronym", "").upper() != acronym.upper()]
    return {"status": "success", "total": len(_CONFERENCE_WATCHLIST)}


# =====================================================================
# ENGINE 3: RESEARCH GAP & NOVELTY RADAR ENDPOINTS
# =====================================================================
@app.post("/api/radar/analyze")
def analyze_research_gap(payload: RadarAnalysisRequest):
    """Audits literature, calculates novelty index, and surfaces unsolved research gaps."""
    service = ResearchGapService(api_key=GEMINI_API_KEY, model=GEMINI_MODEL)
    return service.analyze_gap(
        topic=payload.topic,
        idea_proposal=payload.idea_proposal or "",
        target_domain=payload.target_domain or "Computer Science"
    )


@app.post("/api/radar/upload-pdf")
async def upload_pdf_for_radar(
    file: UploadFile = File(...),
    target_domain: Optional[str] = Form("Computer Science")
):
    """Extracts topic and proposed methodology from an uploaded proposal or paper PDF and runs novelty gap radar."""
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported.")
    
    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    full_text = ""
    total_pages = 0
    extracted_title = ""
    
    try:
        if fitz is not None:
            doc = fitz.open(stream=file_bytes, filetype="pdf")
            total_pages = len(doc)
            meta = doc.metadata or {}
            extracted_title = meta.get("title") or ""
            text_parts = []
            for page in doc:
                text_parts.append(page.get_text("text"))
            full_text = "\n\n".join(text_parts).strip()
            doc.close()
        elif pypdf is not None:
            import io
            reader = pypdf.PdfReader(io.BytesIO(file_bytes))
            total_pages = len(reader.pages)
            meta = reader.metadata
            extracted_title = (getattr(meta, 'title', None) if meta else None) or ""
            text_parts = [p.extract_text() or "" for p in reader.pages]
            full_text = "\n\n".join(text_parts).strip()
    except Exception as e:
        logger.warning(f"Error extracting PDF text for radar: {e}")

    if not full_text:
        import uuid
        temp_path = PDFS_DIR / f"radar_{uuid.uuid4().hex[:8]}_{file.filename}"
        try:
            with open(temp_path, "wb") as f:
                f.write(file_bytes)
            full_text, total_pages = PDFProcessor.extract_verbatim_text(temp_path)
        except Exception as e:
            logger.warning(f"Fallback extraction failed: {e}")
        finally:
            if temp_path.exists():
                try:
                    temp_path.unlink()
                except Exception:
                    pass

    if not full_text:
        raise HTTPException(status_code=400, detail="Could not extract readable text from the uploaded PDF.")

    service = ResearchGapService(api_key=GEMINI_API_KEY, model=GEMINI_MODEL)
    result = service.analyze_from_pdf_text(pdf_text=full_text, filename=file.filename, domain=target_domain or "Computer Science")
    return {
        "success": True,
        "filename": file.filename,
        "total_pages": total_pages,
        "word_count": len(full_text.split()),
        "radar": result
    }


@app.post("/api/radar/chat")
def chat_radar_endpoint(payload: RadarChatRequest):
    """Dynamic interactive deep-dive into research gaps and technical architecture."""
    service = ResearchGapService(api_key=GEMINI_API_KEY, model=GEMINI_MODEL)
    reply = service.chat_gap_deep_dive(
        topic=payload.topic,
        radar_result=payload.radar_result or {},
        user_message=payload.message,
        chat_history=payload.history or []
    )
    return {"reply": reply}


# =====================================================================
# ENGINE 4: AI "REVIEWER #2" SIMULATOR ENDPOINTS
# =====================================================================
@app.post("/api/reviewer/simulate")
def simulate_reviewer_two(payload: ReviewerRequest):
    """Simulates a ruthless Tier-1 peer reviewer critique on draft papers."""
    service = ReviewerSimulatorService(api_key=GEMINI_API_KEY, model=GEMINI_MODEL)
    return service.review_paper(
        title=payload.title,
        abstract=payload.abstract,
        methodology=payload.methodology or "",
        target_venue=payload.target_venue or "NeurIPS / IEEE"
    )


@app.post("/api/reviewer/upload-pdf")
async def upload_pdf_for_reviewer(
    file: UploadFile = File(...),
    target_venue: Optional[str] = Form("NeurIPS / IEEE")
):
    """Audits an uploaded PDF manuscript draft, extracting sections, evaluating methodology, and generating publication improvements."""
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported.")
    
    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    full_text = ""
    total_pages = 0
    extracted_title = ""
    
    try:
        if fitz is not None:
            doc = fitz.open(stream=file_bytes, filetype="pdf")
            total_pages = len(doc)
            meta = doc.metadata or {}
            extracted_title = meta.get("title") or ""
            text_parts = []
            for page in doc:
                text_parts.append(page.get_text("text"))
            full_text = "\n\n".join(text_parts).strip()
            doc.close()
        elif pypdf is not None:
            import io
            reader = pypdf.PdfReader(io.BytesIO(file_bytes))
            total_pages = len(reader.pages)
            meta = reader.metadata
            extracted_title = (getattr(meta, 'title', None) if meta else None) or ""
            text_parts = [p.extract_text() or "" for p in reader.pages]
            full_text = "\n\n".join(text_parts).strip()
    except Exception as e:
        logger.warning(f"Error extracting PDF text for reviewer: {e}")

    if not full_text:
        import uuid
        temp_path = PDFS_DIR / f"rev_{uuid.uuid4().hex[:8]}_{file.filename}"
        try:
            with open(temp_path, "wb") as f:
                f.write(file_bytes)
            full_text, total_pages = PDFProcessor.extract_verbatim_text(temp_path)
        except Exception as e:
            logger.warning(f"Fallback extraction failed: {e}")
        finally:
            if temp_path.exists():
                try:
                    temp_path.unlink()
                except Exception:
                    pass

    if not full_text:
        raise HTTPException(status_code=400, detail="Could not extract readable text from the uploaded PDF.")

    if not extracted_title:
        extracted_title = file.filename.replace(".pdf", "").replace("_", " ").title()

    service = ReviewerSimulatorService(api_key=GEMINI_API_KEY, model=GEMINI_MODEL)
    result = service.review_full_manuscript(full_text=full_text, title=extracted_title, target_venue=target_venue or "NeurIPS / IEEE")
    return {
        "success": True,
        "filename": file.filename,
        "total_pages": total_pages,
        "word_count": len(full_text.split()),
        "review": result
    }


@app.post("/api/reviewer/chat")
def chat_reviewer_endpoint(payload: ReviewerChatRequest):
    """Dynamic author rebuttal coach & interactive follow-up with Reviewer #2."""
    service = ReviewerSimulatorService(api_key=GEMINI_API_KEY, model=GEMINI_MODEL)
    reply = service.chat_rebuttal(
        paper_title=payload.paper_title,
        critique=payload.critique or {},
        user_message=payload.message,
        chat_history=payload.history or []
    )
    return {"reply": reply}


# =====================================================================
# ENGINE 5: FELLOWSHIP, TRAVEL GRANT & FUNDING RADAR ENDPOINTS
# =====================================================================
@app.get("/api/grants/search")
def get_grants(
    query: Optional[str] = "",
    research_work: Optional[str] = "",
    destination: Optional[str] = "All",
    category: Optional[str] = "All"
):
    """Returns doctoral fellowships and student conference travel grants matched by topic and destination."""
    service = FundingScoutService(api_key=GEMINI_API_KEY, model=GEMINI_MODEL)
    return service.search_funding(
        query=query or "",
        research_work=research_work or "",
        destination=destination or "All",
        category=category or "All"
    )


@app.post("/api/grants/search")
def post_grants(payload: FundingSearchRequest):
    """Searches doctoral fellowships and travel grants with live AI expansion."""
    service = FundingScoutService(api_key=GEMINI_API_KEY, model=GEMINI_MODEL)
    return service.search_funding(
        query=payload.query or "",
        research_work=payload.research_work or "",
        destination=payload.destination or "All",
        category=payload.category or "All"
    )


# =====================================================================
# ENGINE 6: TECH SUMMIT & INDUSTRY LAB CONNECTOR ENDPOINTS
# =====================================================================
@app.get("/api/labs/search")
def get_labs(
    query: Optional[str] = "",
    research_work: Optional[str] = "",
    location: Optional[str] = "All",
    item_type: Optional[str] = "All"
):
    """Returns research scientist internships and global tech expos matched by field and preferred location."""
    service = IndustryLabService(api_key=GEMINI_API_KEY, model=GEMINI_MODEL)
    return service.search_labs(
        query=query or "",
        research_work=research_work or "",
        location=location or "All",
        item_type=item_type or "All"
    )


@app.post("/api/labs/search")
def post_labs(payload: LabSearchRequest):
    """Searches research scientist internships and tech summits with live AI expansion."""
    service = IndustryLabService(api_key=GEMINI_API_KEY, model=GEMINI_MODEL)
    return service.search_labs(
        query=payload.query or "",
        research_work=payload.research_work or "",
        location=payload.location or "All",
        item_type=payload.item_type or "All"
    )


# =====================================================================
# ENGINE 7: AUTONOMOUS PHD DIGITAL TWIN & EXECUTIVE CO-PILOT ENDPOINTS
# =====================================================================
@app.get("/api/twin/profile")
def get_twin_profile():
    """Returns Mark Febiri's digital twin knowledge base, synced with febmac.vercel.app."""
    if not TwinAgentService:
        raise HTTPException(status_code=503, detail="TwinAgentService unavailable")
    service = TwinAgentService(api_key=GEMINI_API_KEY, model=GEMINI_MODEL)
    return service.get_profile()


@app.post("/api/twin/sync")
def sync_twin_portfolio(payload: TwinSyncRequest = TwinSyncRequest()):
    """Live re-crawls Mark Febiri's portfolio website to refresh profile knowledge."""
    if not PortfolioSyncService:
        raise HTTPException(status_code=503, detail="PortfolioSyncService unavailable")
    return PortfolioSyncService.live_sync(base_url=payload.url or "https://febmac.vercel.app")


@app.post("/api/twin/update-profile")
def update_twin_profile(payload: TwinUpdateRequest):
    """Updates custom research notes or active focus for the Digital Twin."""
    if not TwinAgentService:
        raise HTTPException(status_code=503, detail="TwinAgentService unavailable")
    service = TwinAgentService(api_key=GEMINI_API_KEY, model=GEMINI_MODEL)
    return service.update_profile(custom_notes=payload.custom_notes, active_focus=payload.active_focus)


@app.post("/api/twin/apply-grant")
def twin_apply_grant(payload: TwinApplyGrantRequest):
    """Autonomous drafter: creates complete grant/fellowship dossier on Mark's behalf."""
    if not TwinAgentService:
        raise HTTPException(status_code=503, detail="TwinAgentService unavailable")
    service = TwinAgentService(api_key=GEMINI_API_KEY, model=GEMINI_MODEL)
    return service.apply_for_grant(grant_title=payload.grant_title, grant_details=payload.grant_details or {})


@app.post("/api/twin/apply-lab")
def twin_apply_lab(payload: TwinApplyLabRequest):
    """Autonomous drafter: creates complete research lab internship pitch & cold email on Mark's behalf."""
    if not TwinAgentService:
        raise HTTPException(status_code=503, detail="TwinAgentService unavailable")
    service = TwinAgentService(api_key=GEMINI_API_KEY, model=GEMINI_MODEL)
    return service.apply_for_lab(lab_title=payload.lab_title, lab_details=payload.lab_details or {})


@app.get("/api/twin/suggestions")
def get_twin_suggestions():
    """Proactive strategic advisor: returns prioritized actions Mark should take over the next 14-60 days."""
    if not TwinAgentService:
        raise HTTPException(status_code=503, detail="TwinAgentService unavailable")
    service = TwinAgentService(api_key=GEMINI_API_KEY, model=GEMINI_MODEL)
    return service.get_strategic_suggestions()


@app.post("/api/twin/chat")
def chat_with_twin(payload: TwinChatRequest):
    """Interactive chat with Mark Febiri's perfectionist digital twin."""
    if not TwinAgentService:
        raise HTTPException(status_code=503, detail="TwinAgentService unavailable")
    service = TwinAgentService(api_key=GEMINI_API_KEY, model=GEMINI_MODEL)
    response_text = service.chat_with_twin(user_message=payload.message, chat_history=payload.history or [])
    return {"reply": response_text}


@app.get("/api/twin/github/status")
def get_twin_github_status():
    """Returns the live connection status of Mark Febiri's GitHub account."""
    if not GitHubConnectorService:
        raise HTTPException(status_code=503, detail="GitHubConnectorService unavailable")
    connector = GitHubConnectorService()
    return connector.get_status()


@app.post("/api/twin/github/connect")
def connect_twin_github(payload: GitHubConnectRequest):
    """Saves GitHub Personal Access Token and verifies credentials against GitHub API."""
    if not GitHubConnectorService:
        raise HTTPException(status_code=503, detail="GitHubConnectorService unavailable")
    connector = GitHubConnectorService()
    result = connector.save_token(token=payload.token, username=payload.username or "Febiri")
    return result


@app.get("/api/twin/github/repos")
def get_twin_github_repos():
    """Fetches Mark Febiri's active repositories directly from GitHub API."""
    if not GitHubConnectorService:
        raise HTTPException(status_code=503, detail="GitHubConnectorService unavailable")
    connector = GitHubConnectorService()
    repos = connector.fetch_live_repositories()
    return {"repos": repos, "total": len(repos)}


@app.post("/api/twin/prepare-application")
def twin_prepare_application(payload: PrepareApplicationRequest):
    """Pre-fills and packages an application dossier for human-in-the-loop 'Check & Proceed'."""
    if not TwinAgentService:
        raise HTTPException(status_code=503, detail="TwinAgentService unavailable")
    service = TwinAgentService(api_key=GEMINI_API_KEY, model=GEMINI_MODEL)
    packet = service.prepare_application_packet(
        opportunity_type=payload.opportunity_type,
        title=payload.title,
        details=payload.details or {}
    )
    return packet


@app.post("/api/twin/dispatch-application")
def twin_dispatch_application(payload: DispatchApplicationRequest):
    """Executes dispatch upon human 'Proceed' approval: creates GitHub issue/log and records dispatch."""
    if not TwinAgentService:
        raise HTTPException(status_code=503, detail="TwinAgentService unavailable")
    service = TwinAgentService(api_key=GEMINI_API_KEY, model=GEMINI_MODEL)
    result = service.dispatch_application(
        packet=payload.packet,
        target_repo=payload.target_repo or "febPhD"
    )
    return result


@app.get("/api/twin/dispatch-history")
def get_twin_dispatch_history():
    """Returns audit log of all autonomous applications prepared and dispatched."""
    if not TwinAgentService:
        raise HTTPException(status_code=503, detail="TwinAgentService unavailable")
    service = TwinAgentService(api_key=GEMINI_API_KEY, model=GEMINI_MODEL)
    history = service.get_dispatch_history()
    return {"history": history, "total": len(history)}


@app.get("/api/health/runtime")
def api_health():
    """Health check endpoint to test runtime status."""
    return {
        "status": "healthy",
        "service": "ProfFeb",
        "serverless": IS_SERVERLESS,
        "database": "connected"
    }


# Safely mount static directory if it exists, without crashing if directory is missing
try:
    if not STATIC_DIR.exists():
        STATIC_DIR.mkdir(parents=True, exist_ok=True)
    if STATIC_DIR.exists():
        app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
except Exception as e:
    logger.warning(f"Static directory could not be mounted: {e}")


def _load_html(filename: str) -> Optional[str]:
    """Search multiple paths for frontend templates and load string content."""
    candidates = [
        FRONTEND_DIR / filename,
        BASE_DIR / "frontend" / filename,
        Path.cwd() / "frontend" / filename,
        Path(__file__).resolve().parent.parent / "frontend" / filename,
    ]
    for p in candidates:
        if p.exists():
            try:
                return p.read_text(encoding="utf-8")
            except Exception:
                pass
    return None


@app.get("/favicon.ico", include_in_schema=False)
def get_favicon():
    favicon_path = STATIC_DIR / "favicon.ico"
    if favicon_path.exists():
        return FileResponse(str(favicon_path), media_type="image/x-icon")
    raise HTTPException(status_code=404, detail="Favicon not found")


# Serve modern white Home page
@app.get("/")
def serve_home():
    content = _load_html("home.html")
    if content:
        return HTMLResponse(content=content)
    return serve_app()


# Serve Intelligent Academic Conference & Event Scout standalone page
@app.get("/conferences")
@app.get("/conferences/")
@app.get("/scout")
@app.get("/events")
def serve_conferences():
    content = _load_html("conferences.html")
    if content:
        return HTMLResponse(content=content)
    return serve_home()


# Serve Zotero Audio Mentor workspace
@app.get("/app")
@app.get("/app/")
@app.get("/library")
@app.get("/reader")
def serve_app():
    content = _load_html("index.html")
    if content:
        return HTMLResponse(content=content)
    return JSONResponse(
        status_code=404,
        content={"message": "Frontend index.html not found. Ensure frontend directory is populated."}
    )


# Serve Engine 03: Research Gap & Novelty Radar
@app.get("/radar")
@app.get("/radar/")
@app.get("/novelty")
def serve_radar():
    content = _load_html("radar.html")
    if content:
        return HTMLResponse(content=content)
    return serve_home()


# Serve Engine 04: AI "Reviewer #2" Harsh Peer-Review Simulator
@app.get("/reviewer")
@app.get("/reviewer/")
@app.get("/peer-review")
def serve_reviewer():
    content = _load_html("reviewer.html")
    if content:
        return HTMLResponse(content=content)
    return serve_home()


# Serve Engine 05: Fellowship, Travel Grant & Funding Radar
@app.get("/grants")
@app.get("/grants/")
@app.get("/funding")
@app.get("/fellowships")
def serve_grants():
    content = _load_html("grants.html")
    if content:
        return HTMLResponse(content=content)
    return serve_home()


# Serve Engine 06: Tech Summit & Industry Research Lab Connector
@app.get("/lab-connector")
@app.get("/lab-connector/")
@app.get("/labs")
@app.get("/labs/")
@app.get("/careers")
@app.get("/summits")
def serve_lab_connector():
    content = _load_html("lab_connector.html")
    if content:
        return HTMLResponse(content=content)
    return serve_home()


# Serve Engine 07: Autonomous PhD Digital Twin & Executive Co-Pilot Studio
@app.get("/agent")
@app.get("/agent/")
@app.get("/twin")
@app.get("/copilot")
def serve_agent():
    content = _load_html("agent.html")
    if content:
        return HTMLResponse(content=content)
    return serve_home()
