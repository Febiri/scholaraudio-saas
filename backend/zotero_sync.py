import os
import sys
import logging
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from typing import List, Dict, Any, Optional
from pyzotero import zotero
from pyzotero.zotero_errors import UserNotAuthorisedError, ResourceNotFoundError, HTTPError
from sqlalchemy.orm import Session

try:
    from backend.config import PDFS_DIR, ZOTERO_LIBRARY_ID, ZOTERO_API_KEY, ZOTERO_LIBRARY_TYPE
    from backend.database import Paper
except ImportError:
    from config import PDFS_DIR, ZOTERO_LIBRARY_ID, ZOTERO_API_KEY, ZOTERO_LIBRARY_TYPE
    from database import Paper

logger = logging.getLogger("zotero_sync")
logging.basicConfig(level=logging.INFO)


class ZoteroSyncService:
    def __init__(
        self,
        library_id: Optional[str] = None,
        library_type: Optional[str] = None,
        api_key: Optional[str] = None,
    ):
        self.library_id = str(library_id or ZOTERO_LIBRARY_ID or "").strip()
        self.library_type = (library_type or ZOTERO_LIBRARY_TYPE or "user").strip().lower()
        self.api_key = str(api_key or ZOTERO_API_KEY or "").strip()

        if not self.library_id or not self.api_key:
            self.client = None
        else:
            try:
                self.client = zotero.Zotero(
                    library_id=self.library_id,
                    library_type=self.library_type,
                    api_key=self.api_key,
                )
            except Exception as e:
                logger.error(f"Failed to initialize Zotero client: {e}")
                self.client = None

    def test_connection(self) -> Dict[str, Any]:
        """Test authentication and read permissions with Zotero Web API."""
        if not self.client:
            return {
                "success": False,
                "message": "Zotero credentials (Library ID and API Key) are not configured."
            }
        try:
            # key_info returns permissions associated with API key
            info = self.client.key_info()
            return {
                "success": True,
                "message": "Connected to Zotero API successfully.",
                "permissions": info
            }
        except UserNotAuthorisedError:
            return {"success": False, "message": "Authentication failed: Invalid API key or unauthorized access."}
        except Exception as e:
            return {"success": False, "message": f"Connection error: {str(e)}"}

    def _format_authors(self, creators: List[Dict[str, Any]]) -> str:
        """Format Zotero creator dictionary list into human-readable author string."""
        if not creators:
            return ""
        author_names = []
        for c in creators:
            creator_type = c.get("creatorType", "author")
            if creator_type in ["author", "editor", "contributor"]:
                first = c.get("firstName", "").strip()
                last = c.get("lastName", "").strip()
                name = c.get("name", "").strip()
                if first and last:
                    author_names.append(f"{first} {last}")
                elif last:
                    author_names.append(last)
                elif name:
                    author_names.append(name)
        if not author_names and creators:
            # fallback to whatever is available
            for c in creators:
                author_names.append(c.get("name", "Unknown"))
        return ", ".join(author_names[:8]) + (" et al." if len(author_names) > 8 else "")

    def _extract_year(self, date_str: str) -> str:
        """Extract 4-digit year from date string."""
        if not date_str:
            return ""
        import re
        match = re.search(r"\b(19\d{2}|20\d{2})\b", str(date_str))
        return match.group(1) if match else str(date_str)[:10]

    def download_pdf_attachment(self, item_key: str) -> Optional[str]:
        """Look up children attachments for an item and download the PDF binary."""
        if not self.client:
            return None

        try:
            children = self.client.children(item_key)
            for child in children:
                data = child.get("data", {})
                item_type = data.get("itemType")
                content_type = data.get("contentType", "")
                filename = data.get("filename", "")

                is_pdf = (
                    item_type == "attachment" and (
                        content_type == "application/pdf" or
                        filename.lower().endswith(".pdf")
                    )
                )

                if is_pdf:
                    attachment_key = child.get("key")
                    pdf_filename = f"{item_key}_{attachment_key}.pdf"
                    target_path = PDFS_DIR / pdf_filename

                    logger.info(f"Downloading PDF attachment {attachment_key} for item {item_key}...")
                    try:
                        self.client.dump(attachment_key, filename=str(target_path))
                        if target_path.exists() and target_path.stat().st_size > 0:
                            logger.info(f"Successfully downloaded PDF to {target_path}")
                            return str(target_path)
                    except Exception as dump_err:
                        logger.warning(f"Failed to dump PDF attachment {attachment_key}: {dump_err}")
                        # If direct file download fails, item might be linked URL or lack file permission
                        continue
        except Exception as e:
            logger.error(f"Error fetching attachments for item {item_key}: {e}")

        return None

    def sync_library(self, db: Session, limit: int = 30, user_id: Optional[str] = None) -> Dict[str, Any]:
        """Fetch recent items from Zotero and upsert into database."""
        if not self.client:
            return {
                "success": False,
                "message": "Zotero client not configured. Please provide Library ID and API Key."
            }

        stats = {
            "total_fetched": 0,
            "new_added": 0,
            "updated": 0,
            "pdfs_found": 0,
            "errors": []
        }

        try:
            # Fetch top-level items sorted by date modified
            items = self.client.top(limit=limit)
            stats["total_fetched"] = len(items)

            for item in items:
                data = item.get("data", {})
                item_type = data.get("itemType", "")
                item_key = data.get("key")

                # Skip annotations, notes, or standalone attachments
                if item_type in ["attachment", "note", "annotation"]:
                    continue

                title = data.get("title", "").strip() or "Untitled Document"
                abstract = data.get("abstractNote", "").strip()
                authors = self._format_authors(data.get("creators", []))
                publication_year = self._extract_year(data.get("date", ""))
                journal = data.get("publicationTitle") or data.get("conferenceName") or data.get("proceedingsTitle") or ""

                # Check if paper already exists in DB
                filter_cond = [Paper.zotero_item_key == item_key]
                if user_id:
                    filter_cond.append(Paper.user_id == user_id)
                paper = db.query(Paper).filter(*filter_cond).first()

                # Attempt PDF download if not already downloaded
                pdf_path = None
                has_pdf = False

                if paper and paper.pdf_path and os.path.exists(paper.pdf_path):
                    pdf_path = paper.pdf_path
                    has_pdf = True
                else:
                    pdf_path = self.download_pdf_attachment(item_key)
                    if pdf_path and os.path.exists(pdf_path):
                        has_pdf = True
                        stats["pdfs_found"] += 1

                if paper:
                    paper.title = title
                    paper.authors = authors
                    paper.abstract = abstract
                    paper.publication_year = publication_year
                    paper.journal = journal
                    if user_id and not paper.user_id:
                        paper.user_id = user_id
                    if pdf_path:
                        paper.pdf_path = pdf_path
                        paper.has_pdf = has_pdf
                    stats["updated"] += 1
                else:
                    new_paper = Paper(
                        user_id=user_id,
                        zotero_item_key=item_key,
                        title=title,
                        authors=authors,
                        abstract=abstract,
                        publication_year=publication_year,
                        journal=journal,
                        pdf_path=pdf_path,
                        has_pdf=has_pdf,
                        status="Pending"
                    )
                    db.add(new_paper)
                    stats["new_added"] += 1

            db.commit()
            return {
                "success": True,
                "message": f"Successfully synced {stats['new_added']} new and {stats['updated']} updated papers from Zotero.",
                "stats": stats
            }

        except UserNotAuthorisedError:
            return {"success": False, "message": "Zotero authentication error: Invalid User ID or API Key."}
        except HTTPError as e:
            return {"success": False, "message": f"Zotero API HTTP Error: {str(e)}"}
        except Exception as e:
            try:
                db.rollback()
            except Exception:
                pass
            if "readonly" in str(e).lower() or "read-only" in str(e).lower():
                logger.error(f"Read-only SQLite error caught during Zotero sync: {e}")
                return {
                    "success": False,
                    "message": "Database storage was temporarily read-only. Engine has re-routed to writable temporary storage. Please click Sync Zotero once more."
                }
            logger.error(f"Zotero sync failed: {e}", exc_info=True)
            return {"success": False, "message": f"Sync failed: {str(e)}"}
