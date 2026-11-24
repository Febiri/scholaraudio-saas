import sys
from pathlib import Path
_CURRENT = Path(__file__).resolve().parent
_ROOT = _CURRENT if (_CURRENT / "data").exists() else _CURRENT.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from datetime import datetime
from typing import Generator
from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, Boolean, Float, LargeBinary, text, event
from sqlalchemy.orm import declarative_base, sessionmaker, Session, deferred

try:
    from backend.config import DATABASE_URL
except ImportError:
    from config import DATABASE_URL

import logging

logger = logging.getLogger("database")

def _create_safe_engine(url: str):
    import os
    import tempfile
    from sqlalchemy.pool import StaticPool

    def _normalize_db_url(raw: str) -> str:
        if not raw:
            return raw
        clean = raw.strip().strip("'").strip('"')
        if clean.startswith("postgres://"):
            clean = "postgresql://" + clean[len("postgres://"):]
        return clean

    norm_url = _normalize_db_url(url)

    def _is_engine_writable(eng) -> bool:
        if eng.url.drivername.startswith("sqlite"):
            db_path = eng.url.database
            if not db_path or db_path == ":memory:":
                return True
            p = Path(db_path)
            try:
                if p.exists():
                    return os.access(p, os.W_OK)
                else:
                    return os.access(p.parent if p.parent.exists() else Path("."), os.W_OK)
            except Exception:
                return False
        else:
            try:
                with eng.connect() as conn:
                    conn.execute(text("SELECT 1"))
                return True
            except Exception as e:
                logger.warning(f"Engine {eng.url} connection check failed: {e}")
                return False

    def _configure_sqlite_pragmas(eng):
        @event.listens_for(eng, "connect")
        def set_sqlite_pragma(dbapi_connection, connection_record):
            cursor = dbapi_connection.cursor()
            try:
                cursor.execute("PRAGMA journal_mode = WAL")
                cursor.execute("PRAGMA synchronous = NORMAL")
                cursor.execute("PRAGMA busy_timeout = 30000")
            except Exception:
                pass
            finally:
                cursor.close()

    # Attempt 1: Configured database URL (Supabase PostgreSQL or SQLite)
    if norm_url.startswith("postgresql"):
        try:
            eng = create_engine(
                norm_url,
                pool_pre_ping=True,
                pool_recycle=300,
                pool_size=10,
                max_overflow=20
            )
            if _is_engine_writable(eng):
                logger.info(f"Successfully verified writable PostgreSQL/Supabase database at {eng.url.host}")
                return eng
        except Exception as e:
            logger.warning(f"PostgreSQL connection failed: {e}. Trying pg8000 dialect...")
            try:
                pg8000_url = norm_url.replace("postgresql://", "postgresql+pg8000://").replace("+psycopg2", "+pg8000")
                eng = create_engine(pg8000_url, pool_pre_ping=True, pool_recycle=300)
                if _is_engine_writable(eng):
                    logger.info(f"Successfully connected via pg8000 driver to {eng.url.host}")
                    return eng
            except Exception as e2:
                logger.warning(f"pg8000 fallback also failed: {e2}")
    else:
        try:
            eng = create_engine(
                norm_url,
                connect_args={"check_same_thread": False, "timeout": 30.0} if norm_url.startswith("sqlite") else {}
            )
            if norm_url.startswith("sqlite") and ":memory:" not in norm_url:
                _configure_sqlite_pragmas(eng)
            if _is_engine_writable(eng):
                return eng
        except Exception as e:
            logger.warning(f"Failed to initialize database at {norm_url}: {e}")

    # Attempt 2: Writable system temp file database
    try:
        tmp_dir = Path("/tmp") if (os.name != "nt" or Path("/tmp").exists()) else Path(tempfile.gettempdir())
        tmp_db_file = tmp_dir / "zotero_audio.db"
        if not tmp_db_file.exists():
            base_db = _ROOT / "zotero_audio.db"
            if base_db.exists():
                try:
                    import shutil
                    shutil.copyfile(base_db, tmp_db_file)
                    try:
                        os.chmod(tmp_db_file, 0o666)
                    except Exception:
                        pass
                except Exception:
                    pass
        tmp_url = f"sqlite:///{tmp_db_file.as_posix()}"
        eng = create_engine(tmp_url, connect_args={"check_same_thread": False, "timeout": 30.0})
        _configure_sqlite_pragmas(eng)
        if _is_engine_writable(eng):
            logger.info(f"Using verified writable temporary SQLite database at {tmp_url}")
            return eng
    except Exception as e:
        logger.warning(f"Temporary database fallback failed: {e}")

    # Attempt 3: In-memory SQLite with StaticPool (only if disk is truly unavailable)
    logger.warning("Falling back to in-memory SQLite database with StaticPool.")
    return create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False, "timeout": 30.0},
        poolclass=StaticPool
    )

engine = _create_safe_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class Paper(Base):
    __tablename__ = "papers"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id = Column(String(64), nullable=True, index=True)
    zotero_item_key = Column(String(64), unique=True, index=True, nullable=True)
    title = Column(String(512), nullable=False, index=True)
    authors = Column(String(512), default="")
    abstract = Column(Text, default="")
    publication_year = Column(String(32), default="")
    journal = Column(String(256), default="")
    
    # File & Path attributes
    pdf_path = Column(String(512), nullable=True)
    has_pdf = Column(Boolean, default=False)
    
    # AI Summary attributes
    summary_text = Column(Text, nullable=True)
    summary_problem = Column(Text, nullable=True)
    summary_methodology = Column(Text, nullable=True)
    summary_results = Column(Text, nullable=True)
    summary_limitations = Column(Text, nullable=True)

    # Full Paper Reading attributes
    full_text = Column(Text, nullable=True)
    
    # Audio attributes
    audio_mode = Column(String(32), default="summary")  # "summary" or "full_paper"
    audio_path = Column(String(512), nullable=True)
    audio_duration = Column(Float, default=0.0)
    summary_audio_path = Column(String(512), nullable=True)
    summary_audio_duration = Column(Float, default=0.0)
    full_audio_path = Column(String(512), nullable=True)
    full_audio_duration = Column(Float, default=0.0)
    summary_audio_blob = deferred(Column(LargeBinary, nullable=True))
    full_audio_blob = deferred(Column(LargeBinary, nullable=True))
    voice_used = Column(String(64), default="en-US-ChristopherNeural")
    
    # Processing status: "Pending", "Processing", "Ready", "Failed"
    status = Column(String(32), default="Pending", index=True)
    error_message = Column(Text, nullable=True)
    
    # Notes & Chat attributes (Permanently Persisted in Database)
    notes_json = Column(Text, default="[]")
    chat_history_json = Column(Text, default="[]")

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self, include_full_text: bool = True):
        # Resolve active audio path and duration
        active_audio_path = self.audio_path
        active_audio_duration = self.audio_duration or 0.0
        
        # If active audio path is not set but one of the specific paths exists, fallback gracefully
        if not active_audio_path:
            if self.audio_mode == "full_paper" and self.full_audio_path:
                active_audio_path = self.full_audio_path
                active_audio_duration = self.full_audio_duration or 0.0
            elif self.summary_audio_path:
                active_audio_path = self.summary_audio_path
                active_audio_duration = self.summary_audio_duration or 0.0

        d = {
            "id": self.id,
            "user_id": getattr(self, "user_id", None),
            "zotero_item_key": self.zotero_item_key,
            "title": self.title,
            "authors": self.authors,
            "abstract": self.abstract,
            "publication_year": self.publication_year,
            "journal": self.journal,
            "pdf_path": self.pdf_path,
            "has_pdf": self.has_pdf,
            "has_full_text": bool(self.full_text and self.full_text.strip()),
            "summary_text": self.summary_text,
            "summary_problem": self.summary_problem,
            "summary_methodology": self.summary_methodology,
            "summary_results": self.summary_results,
            "summary_limitations": self.summary_limitations,
            "full_text": self.full_text if include_full_text else None,
            "audio_mode": self.audio_mode or "summary",
            "audio_path": active_audio_path,
            "audio_duration": active_audio_duration,
            "summary_audio_path": self.summary_audio_path or (self.audio_path if self.audio_mode == "summary" else None),
            "summary_audio_duration": self.summary_audio_duration or (self.audio_duration if self.audio_mode == "summary" else 0.0),
            "full_audio_path": self.full_audio_path or (self.audio_path if self.audio_mode == "full_paper" else None),
            "full_audio_duration": self.full_audio_duration or (self.audio_duration if self.audio_mode == "full_paper" else 0.0),
            "has_summary_audio": bool(self.summary_audio_path or (self.audio_path and self.audio_mode == "summary")),
            "has_full_audio": bool(self.full_audio_path or (self.audio_path and self.audio_mode == "full_paper")),
            "voice_used": self.voice_used,
            "status": self.status,
            "notes": json.loads(self.notes_json) if self.notes_json else [],
            "chat_history": json.loads(self.chat_history_json) if self.chat_history_json else [],
            "error_message": self.error_message,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
        return d


def init_db():
    try:
        Base.metadata.create_all(bind=engine)
    except Exception as e:
        logger.warning(f"Warning: could not execute create_all on database: {e}")
        return

    # Automatically migrate columns if missing (SQLite or PostgreSQL)
    try:
        dialect_name = getattr(engine.dialect, "name", "sqlite")
        if dialect_name == "sqlite":
            with engine.connect() as conn:
                cursor = conn.connection.cursor()
                cursor.execute("PRAGMA table_info(papers)")
                existing_cols = [row[1] for row in cursor.fetchall()]
                new_cols = [
                    ("user_id", "VARCHAR(64)"),
                    ("notes_json", "TEXT DEFAULT '[]'"),
                    ("chat_history_json", "TEXT DEFAULT '[]'"),
                    ("full_text", "TEXT"),
                    ("audio_mode", "VARCHAR(32) DEFAULT 'summary'"),
                    ("summary_audio_path", "VARCHAR(512)"),
                    ("summary_audio_duration", "FLOAT DEFAULT 0.0"),
                    ("full_audio_path", "VARCHAR(512)"),
                    ("full_audio_duration", "FLOAT DEFAULT 0.0"),
                    ("summary_audio_blob", "BLOB"),
                    ("full_audio_blob", "BLOB"),
                ]
                for col_name, col_def in new_cols:
                    if col_name not in existing_cols:
                        cursor.execute(f"ALTER TABLE papers ADD COLUMN {col_name} {col_def}")
                conn.connection.commit()
        elif dialect_name == "postgresql":
            with engine.begin() as conn:
                pg_cols = [
                    ("user_id", "VARCHAR(64)"),
                    ("notes_json", "TEXT DEFAULT '[]'"),
                    ("chat_history_json", "TEXT DEFAULT '[]'"),
                    ("full_text", "TEXT"),
                    ("audio_mode", "VARCHAR(32) DEFAULT 'summary'"),
                    ("summary_audio_path", "VARCHAR(512)"),
                    ("summary_audio_duration", "FLOAT DEFAULT 0.0"),
                    ("full_audio_path", "VARCHAR(512)"),
                    ("full_audio_duration", "FLOAT DEFAULT 0.0"),
                    ("summary_audio_blob", "BYTEA"),
                    ("full_audio_blob", "BYTEA"),
                ]
                for col_name, col_def in pg_cols:
                    conn.execute(text(f"ALTER TABLE papers ADD COLUMN IF NOT EXISTS {col_name} {col_def}"))
    except Exception as e:
        logger.warning(f"Database migration check notice: {e}")

    # Backfill: If existing papers have audio files on local disk but blobs are not yet populated,
    # read the audio files and cache them into the database so they are permanently preserved.
    try:
        from backend.config import AUDIO_DIR, STATIC_DIR
        search_dirs = [AUDIO_DIR, STATIC_DIR / "audio"]
        db = SessionLocal()
        try:
            # Query only papers where at least one audio blob is missing
            papers_to_backfill = db.query(Paper).filter(
                (Paper.summary_audio_blob.is_(None)) | (Paper.full_audio_blob.is_(None))
            ).all()
            updated_count = 0
            for paper in papers_to_backfill:
                # Check summary audio
                if paper.summary_audio_blob is None:
                    candidate = None
                    if paper.summary_audio_path:
                        fname = Path(paper.summary_audio_path).name
                        for sdir in search_dirs:
                            p = sdir / fname
                            if p.exists() and p.stat().st_size > 0:
                                candidate = p
                                break
                    if not candidate:
                        # Glob search for summary mp3
                        for sdir in search_dirs:
                            if sdir.exists():
                                matches = [f for f in sdir.glob(f"paper_{paper.id}_*.mp3") if "_full_" not in f.name]
                                if matches and matches[0].stat().st_size > 0:
                                    candidate = matches[0]
                                    paper.summary_audio_path = f"/api/audio/{candidate.name}"
                                    break
                    if candidate:
                        paper.summary_audio_blob = candidate.read_bytes()
                        updated_count += 1

                # Check full audio (store in DB if under 25MB threshold)
                if paper.full_audio_blob is None:
                    candidate = None
                    if paper.full_audio_path:
                        fname = Path(paper.full_audio_path).name
                        for sdir in search_dirs:
                            p = sdir / fname
                            if p.exists() and p.stat().st_size > 0:
                                candidate = p
                                break
                    if not candidate:
                        # Glob search for full mp3
                        for sdir in search_dirs:
                            if sdir.exists():
                                matches = [f for f in sdir.glob(f"paper_{paper.id}_full_*.mp3")]
                                if matches and matches[0].stat().st_size > 0:
                                    candidate = matches[0]
                                    paper.full_audio_path = f"/api/audio/{candidate.name}"
                                    break
                    if candidate and candidate.stat().st_size < 25 * 1024 * 1024:
                        paper.full_audio_blob = candidate.read_bytes()
                        updated_count += 1

            if updated_count > 0:
                db.commit()
                logger.info(f"Backfilled {updated_count} existing audio tracks into database blobs for persistent storage.")
        finally:
            db.close()
    except Exception as e:
        logger.warning(f"Audio blob backfill notice: {e}")

    # Auto-seed initial research library if database is empty (critical for ephemeral serverless / Vercel instances)
    try:
        db = SessionLocal()
        try:
            if db.query(Paper).count() == 0:
                seed_file = _ROOT / "data" / "seed_papers.json"
                if seed_file.exists():
                    import json
                    seed_papers = json.loads(seed_file.read_text(encoding="utf-8"))
                    for sp in seed_papers:
                        paper = Paper(
                            zotero_item_key=sp.get("zotero_item_key"),
                            title=sp.get("title") or "Untitled Document",
                            authors=sp.get("authors") or "",
                            abstract=sp.get("abstract") or "",
                            publication_year=sp.get("publication_year") or "",
                            journal=sp.get("journal") or "",
                            pdf_path=sp.get("pdf_path"),
                            has_pdf=sp.get("has_pdf", False),
                            summary_text=sp.get("summary_text"),
                            summary_problem=sp.get("summary_problem"),
                            summary_methodology=sp.get("summary_methodology"),
                            summary_results=sp.get("summary_results"),
                            summary_limitations=sp.get("summary_limitations"),
                            full_text=sp.get("full_text"),
                            audio_mode=sp.get("audio_mode") or "summary",
                            audio_path=sp.get("audio_path"),
                            audio_duration=sp.get("audio_duration", 0.0),
                            summary_audio_path=sp.get("summary_audio_path"),
                            summary_audio_duration=sp.get("summary_audio_duration", 0.0),
                            full_audio_path=sp.get("full_audio_path"),
                            full_audio_duration=sp.get("full_audio_duration", 0.0),
                            voice_used=sp.get("voice_used") or "en-NG-AbeoNeural",
                            status=sp.get("status") or "Ready"
                        )
                        db.add(paper)
                    db.commit()
                    logger.info(f"Auto-seeded {len(seed_papers)} papers into clean database.")
        finally:
            db.close()
    except Exception as seed_err:
        logger.warning(f"Auto-seed check notice: {seed_err}")


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

