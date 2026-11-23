import sys
from pathlib import Path
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import zlib
from datetime import datetime
from typing import Generator, Optional, Tuple, Union
from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, Boolean, Float, LargeBinary, ForeignKey, UniqueConstraint
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
    from sqlalchemy import text
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
        try:
            with eng.begin() as conn:
                conn.execute(text("CREATE TABLE IF NOT EXISTS _zam_rw_check (id INTEGER PRIMARY KEY)"))
                conn.execute(text("DROP TABLE IF EXISTS _zam_rw_check"))
            return True
        except Exception as e:
            logger.warning(f"Engine {eng.url} failed write verification: {e}")
            return False

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
                connect_args={"check_same_thread": False} if norm_url.startswith("sqlite") else {}
            )
            if _is_engine_writable(eng):
                return eng
        except Exception as e:
            logger.warning(f"Failed to initialize database at {norm_url}: {e}")

    # Attempt 2: Writable system temp file database
    try:
        tmp_dir = Path("/tmp") if (os.name != "nt" or Path("/tmp").exists()) else Path(tempfile.gettempdir())
        tmp_db_file = tmp_dir / "zotero_audio.db"
        if not tmp_db_file.exists():
            # Try to copy existing base db content if available
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
        eng = create_engine(tmp_url, connect_args={"check_same_thread": False})
        if _is_engine_writable(eng):
            logger.info(f"Using verified writable temporary SQLite database at {tmp_url}")
            return eng
    except Exception as e:
        logger.warning(f"Temporary database fallback failed: {e}")

    # Attempt 3: In-memory SQLite with StaticPool (always 100% writable, zero-disk)
    logger.warning("Falling back to in-memory SQLite database with StaticPool.")
    return create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool
    )

engine = _create_safe_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class Paper(Base):
    __tablename__ = "papers"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id = Column(String(64), index=True, nullable=True)
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
    voice_used = Column(String(64), default="en-US-ChristopherNeural")
    
    # Processing status: "Pending", "Processing", "Ready", "Failed"
    status = Column(String(32), default="Pending", index=True)
    error_message = Column(Text, nullable=True)
    
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
            "user_id": self.user_id,
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
            "error_message": self.error_message,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
        return d


class Note(Base):
    __tablename__ = "notes"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id = Column(String(64), index=True, nullable=True)
    paper_id = Column(Integer, index=True, nullable=True)
    content = Column(Text, nullable=False)
    tags = Column(String(256), default="")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "paper_id": self.paper_id,
            "content": self.content,
            "tags": self.tags,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None
        }


class ConferenceWatchlist(Base):
    __tablename__ = "conference_watchlists"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id = Column(String(64), index=True, nullable=True)
    conference_name = Column(String(512), nullable=False)
    acronym = Column(String(64), default="")
    core_rank = Column(String(32), default="")
    submission_deadline = Column(String(128), default="")
    location = Column(String(256), default="")
    travel_grant = Column(String(256), default="")
    notes = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "conference_name": self.conference_name,
            "acronym": self.acronym,
            "core_rank": self.core_rank,
            "submission_deadline": self.submission_deadline,
            "location": self.location,
            "travel_grant": self.travel_grant,
            "notes": self.notes,
            "created_at": self.created_at.isoformat() if self.created_at else None
        }


class PaperAudio(Base):
    """
    Space-optimized binary cache for generated paper audio.
    Audio bytes are stored using zlib compression on top of MP3 mono speech,
    ensuring >95% storage efficiency while eliminating redundant re-synthesis on startup.
    Deferred loading ensures the audio payload is only fetched when explicitly accessed.
    """
    __tablename__ = "paper_audio"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    paper_id = Column(Integer, ForeignKey("papers.id", ondelete="CASCADE"), index=True, nullable=False)
    user_id = Column(String(64), index=True, nullable=True)
    mode = Column(String(32), default="summary")  # "summary" or "full_paper"
    voice = Column(String(64), nullable=True)
    duration = Column(Float, default=0.0)
    audio_format = Column(String(16), default="mp3_zlib")
    audio_bytes = deferred(Column(LargeBinary, nullable=False))
    file_size_bytes = Column(Integer, default=0)
    compressed_size_bytes = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("paper_id", "mode", name="uq_paper_audio_mode"),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "paper_id": self.paper_id,
            "user_id": self.user_id,
            "mode": self.mode,
            "voice": self.voice,
            "duration": self.duration,
            "file_size_bytes": self.file_size_bytes,
            "compressed_size_bytes": self.compressed_size_bytes,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


def save_paper_audio(
    db: Session,
    paper_id: int,
    mode: str,
    voice: str,
    duration: float,
    audio_data_or_path: Union[bytes, str, Path],
    user_id: Optional[str] = None
) -> Optional[PaperAudio]:
    """
    Saves generated speech audio into the database in a space-optimized format (zlib-compressed MP3).
    Once saved, the audio remains persistent across server restarts and new launches.
    """
    try:
        if isinstance(audio_data_or_path, (str, Path)):
            p = Path(audio_data_or_path)
            if not p.exists():
                return None
            raw_bytes = p.read_bytes()
        elif isinstance(audio_data_or_path, (bytes, bytearray)):
            raw_bytes = bytes(audio_data_or_path)
        else:
            return None

        if not raw_bytes:
            return None

        compressed_bytes = zlib.compress(raw_bytes, level=9)

        record = db.query(PaperAudio).filter(
            PaperAudio.paper_id == paper_id,
            PaperAudio.mode == mode
        ).first()

        if not record:
            record = PaperAudio(
                paper_id=paper_id,
                user_id=user_id,
                mode=mode,
                voice=voice,
                duration=duration,
                audio_format="mp3_zlib",
                audio_bytes=compressed_bytes,
                file_size_bytes=len(raw_bytes),
                compressed_size_bytes=len(compressed_bytes)
            )
            db.add(record)
        else:
            if user_id:
                record.user_id = user_id
            record.voice = voice
            record.duration = duration
            record.audio_bytes = compressed_bytes
            record.file_size_bytes = len(raw_bytes)
            record.compressed_size_bytes = len(compressed_bytes)
            record.updated_at = datetime.utcnow()

        db.commit()
        db.refresh(record)
        logger.info(
            f"Cached audio in DB for paper {paper_id} ({mode}): "
            f"{len(raw_bytes)} bytes -> {len(compressed_bytes)} bytes ({round((len(compressed_bytes)/max(1, len(raw_bytes)))*100, 1)}%)"
        )
        return record
    except Exception as e:
        logger.error(f"Failed to save paper audio to database: {e}")
        db.rollback()
        return None


def get_paper_audio(db: Session, paper_id: int, mode: str = "summary") -> Optional[Tuple[bytes, float, str]]:
    """
    Retrieves and decompresses audio bytes from the database.
    Returns (raw_mp3_bytes, duration, voice) or None.
    """
    try:
        record = db.query(PaperAudio).filter(
            PaperAudio.paper_id == paper_id,
            PaperAudio.mode == mode
        ).first()

        if not record or not record.audio_bytes:
            return None

        if record.audio_format == "mp3_zlib":
            raw_bytes = zlib.decompress(record.audio_bytes)
        else:
            raw_bytes = record.audio_bytes

        return raw_bytes, record.duration or 0.0, record.voice or ""
    except Exception as e:
        logger.error(f"Failed to retrieve paper audio from database: {e}")
        return None


def has_paper_audio(db: Session, paper_id: int, mode: str = "summary") -> bool:
    """Checks whether audio for the paper and mode already exists in the database."""
    try:
        count = db.query(PaperAudio.id).filter(
            PaperAudio.paper_id == paper_id,
            PaperAudio.mode == mode
        ).count()
        return count > 0
    except Exception:
        return False


def restore_paper_audio_file(db: Session, paper_id: int, mode: str, target_path: Union[str, Path]) -> bool:
    """
    Restores an audio file to disk from the database cache without re-synthesizing.
    """
    audio_info = get_paper_audio(db, paper_id=paper_id, mode=mode)
    if not audio_info:
        return False
    raw_bytes, _, _ = audio_info
    target = Path(target_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(raw_bytes)
    return True


def init_db():
    try:
        Base.metadata.create_all(bind=engine)
    except Exception as e:
        logger.warning(f"Warning: could not execute create_all on database: {e}")
        return

    # Automatically migrate SQLite columns if missing
    try:
        with engine.connect() as conn:
            cursor = conn.connection.cursor()
            cursor.execute("PRAGMA table_info(papers)")
            existing_cols = [row[1] for row in cursor.fetchall()]
            new_cols = [
                ("user_id", "VARCHAR(64)"),
                ("full_text", "TEXT"),
                ("audio_mode", "VARCHAR(32) DEFAULT 'summary'"),
                ("summary_audio_path", "VARCHAR(512)"),
                ("summary_audio_duration", "FLOAT DEFAULT 0.0"),
                ("full_audio_path", "VARCHAR(512)"),
                ("full_audio_duration", "FLOAT DEFAULT 0.0"),
            ]
            for col_name, col_def in new_cols:
                if col_name not in existing_cols:
                    cursor.execute(f"ALTER TABLE papers ADD COLUMN {col_name} {col_def}")
            conn.connection.commit()
    except Exception as e:
        # Pass if not SQLite or column already added
        pass


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

