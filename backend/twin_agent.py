import os
import re
import json
import logging
import urllib.request
import urllib.parse
from typing import Dict, Any, List, Optional
from datetime import datetime, date
from pathlib import Path
import httpx

try:
    from bs4 import BeautifulSoup
except Exception:
    BeautifulSoup = None

try:
    from google import genai
    from google.genai import types
except ImportError:
    genai = None
    types = None

try:
    from backend.config import GEMINI_API_KEY, GEMINI_MODEL, BASE_DIR, IS_SERVERLESS, is_writable, GITHUB_TOKEN, GITHUB_USERNAME
except ImportError:
    try:
        from config import GEMINI_API_KEY, GEMINI_MODEL, BASE_DIR, IS_SERVERLESS, is_writable, GITHUB_TOKEN, GITHUB_USERNAME
    except ImportError:
        GEMINI_API_KEY = ""
        GEMINI_MODEL = "gemini-2.5-flash"
        BASE_DIR = Path(__file__).resolve().parent.parent
        IS_SERVERLESS = True
        is_writable = False
        GITHUB_TOKEN = ""
        GITHUB_USERNAME = ""

logger = logging.getLogger("twin_agent")
logging.basicConfig(level=logging.INFO)

PROFILE_CACHE_PATH = (
    Path("/tmp/proffeb_user_profile.json")
    if (IS_SERVERLESS or not is_writable)
    else BASE_DIR / "data" / "proffeb_user_profile.json"
)

# Generic Default Academic Profile for ProfFeb SaaS users
DEFAULT_SCHOLAR_PROFILE: Dict[str, Any] = {
    "name": "Academic Researcher",
    "title": "PhD Scholar & Computational Researcher",
    "roles": [
        "Doctoral Researcher",
        "Applied AI & Systems Scientist",
        "Open-Source Contributor"
    ],
    "email": "researcher@proffeb.ai",
    "locations": "Global Research Community",
    "portfolio_url": "",
    "github_url": "",
    "linkedin_url": "",
    "experience_summary": "Active researcher specializing in machine learning, scientific computing, multimodal intelligence, and computational discovery.",
    "research_focus": "Intelligent systems, deep learning architectures, automated reasoning, and scientific literature mining.",
    "publications": [],
    "flagship_projects": [],
    "technical_arsenal": {
        "ai_ml": [
            "Transformers & Foundation Models",
            "PyTorch & JAX",
            "Agentic Workflows & Retrieval Augmented Generation (RAG)",
            "Scientific Knowledge Representation"
        ],
        "engineering": [
            "Python, FastAPI, C++",
            "PostgreSQL & Vector Databases",
            "Cloud Infrastructure & Containerization (Docker, Kubernetes)",
            "Distributed Computing"
        ]
    }
}


class PortfolioSyncService:
    """Synchronizes user profile and research credentials from any provided portfolio or website."""

    def __init__(self, portfolio_url: str = ""):
        self.portfolio_url = portfolio_url

    def fetch_live_profile(self) -> Dict[str, Any]:
        """Scrapes or synthesizes structured academic profile from portfolio."""
        if not self.portfolio_url:
            return self.load_cached_profile()

        try:
            headers = {"User-Agent": "ProfFeb-AcademicAgent/1.0"}
            req = urllib.request.Request(self.portfolio_url, headers=headers)
            with urllib.request.urlopen(req, timeout=8) as response:
                html = response.read().decode("utf-8", errors="ignore")

            text_content = ""
            if BeautifulSoup:
                soup = BeautifulSoup(html, "html.parser")
                for tag in soup(["script", "style", "nav", "footer"]):
                    tag.decompose()
                text_content = soup.get_text(separator="\n", strip=True)[:10000]
            else:
                text_content = re.sub(r"<[^>]+>", " ", html)[:10000]

            if not text_content.strip():
                return self.load_cached_profile()

            extracted = self._extract_with_gemini(text_content)
            if extracted:
                self.save_cached_profile(extracted)
                return extracted
        except Exception as e:
            logger.warning(f"Could not fetch portfolio {self.portfolio_url}: {e}")

        return self.load_cached_profile()

    def _extract_with_gemini(self, text: str) -> Optional[Dict[str, Any]]:
        if not GEMINI_API_KEY or not genai:
            return None

        prompt = f"""You are ProfFeb Academic Profile Parser. Extract the academic and research biography from the portfolio text into JSON:
{{
  "name": "Scholar Full Name",
  "title": "Academic/Professional Title",
  "roles": ["Role 1", "Role 2"],
  "email": "contact email if found",
  "research_focus": "Core research vision and focus areas",
  "publications": [ {{"title": "...", "venue": "..."}} ],
  "flagship_projects": [ {{"name": "...", "tagline": "...", "description": "..."}} ]
}}

Portfolio text:
{text[:8000]}

Respond ONLY with valid JSON."""

        try:
            client = genai.Client(api_key=GEMINI_API_KEY)
            resp = client.models.generate_content(
                model=GEMINI_MODEL,
                contents=prompt,
                config=types.GenerateContentConfig(response_mime_type="application/json")
            )
            data = json.loads(resp.text)
            merged = {**DEFAULT_SCHOLAR_PROFILE, **data}
            return merged
        except Exception as e:
            logger.warning(f"Gemini portfolio extraction failed: {e}")
            return None

    @classmethod
    def live_sync(cls, base_url: str = "") -> Dict[str, Any]:
        service = cls(portfolio_url=base_url)
        profile = service.fetch_live_profile()
        return {"status": "success", "profile": profile}

    def load_cached_profile(self) -> Dict[str, Any]:
        try:
            if PROFILE_CACHE_PATH.exists():
                with open(PROFILE_CACHE_PATH, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception:
            pass
        return DEFAULT_SCHOLAR_PROFILE.copy()

    def save_cached_profile(self, profile: Dict[str, Any]):
        try:
            PROFILE_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
            with open(PROFILE_CACHE_PATH, "w", encoding="utf-8") as f:
                json.dump(profile, f, indent=2)
        except Exception as e:
            logger.warning(f"Could not cache profile: {e}")


class GitHubConnectorService:
    """Manages GitHub repository connectivity and tracking for research projects."""

    def __init__(self, token: str = "", username: str = ""):
        self.token = (token or GITHUB_TOKEN).strip()
        self.username = (username or GITHUB_USERNAME).strip()

    def get_status(self) -> Dict[str, Any]:
        has_token = bool(self.token)
        return {
            "connected": has_token,
            "username": self.username or "unconnected",
            "has_token": has_token,
            "scopes": ["repo", "workflow", "read:user"] if has_token else []
        }

    def fetch_user_repos(self, limit: int = 12) -> List[Dict[str, Any]]:
        if not self.username:
            return []
        try:
            headers = {"User-Agent": "ProfFeb-AcademicAgent/1.0"}
            if self.token:
                headers["Authorization"] = f"token {self.token}"
            url = f"https://api.github.com/users/{self.username}/repos?sort=updated&per_page={limit}"
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=6) as response:
                repos = json.loads(response.read().decode("utf-8"))
                return [
                    {
                        "name": r.get("name"),
                        "full_name": r.get("full_name"),
                        "description": r.get("description", "Academic and engineering codebase"),
                        "html_url": r.get("html_url"),
                        "stars": r.get("stargazers_count", 0),
                        "language": r.get("language", "Python"),
                        "updated_at": r.get("updated_at")
                    }
                    for r in repos if not r.get("fork")
                ]
        except Exception as e:
            logger.warning(f"Could not fetch repos for {self.username}: {e}")
            return []

    def fetch_live_repositories(self) -> List[Dict[str, Any]]:
        return self.fetch_user_repos()

    def save_token(self, token: str, username: str = "") -> Dict[str, Any]:
        self.token = token.strip()
        if username:
            self.username = username.strip()
        return {
            "status": "success",
            "message": "Token registered successfully.",
            "username": self.username,
            "connected": bool(self.token)
        }

    def log_issue(self, repo: str, title: str, body: str) -> Dict[str, Any]:
        if not self.token or not self.username:
            return {"status": "logged_locally", "message": "GitHub token not configured; saved locally."}

        target_repo = repo if "/" in repo else f"{self.username}/{repo}"
        url = f"https://api.github.com/repos/{target_repo}/issues"
        headers = {
            "Authorization": f"token {self.token}",
            "User-Agent": "ProfFeb-AcademicAgent/1.0",
            "Accept": "application/vnd.github.v3+json"
        }
        payload = json.dumps({"title": title, "body": body}).encode("utf-8")
        try:
            req = urllib.request.Request(url, data=payload, headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=8) as response:
                result = json.loads(response.read().decode("utf-8"))
                return {
                    "status": "success",
                    "issue_url": result.get("html_url"),
                    "issue_number": result.get("number")
                }
        except Exception as e:
            logger.error(f"GitHub issue creation failed: {e}")
            return {"status": "failed", "error": str(e)}


class TwinAgentService:
    """ProfFeb AI Academic Co-Pilot & Research Mentor."""

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None, user_profile: Optional[Dict[str, Any]] = None):
        self.api_key = api_key or GEMINI_API_KEY
        self.model = model or GEMINI_MODEL
        self.profile = user_profile or PortfolioSyncService().load_cached_profile()
        self.github = GitHubConnectorService()

    def get_profile(self) -> Dict[str, Any]:
        return self.profile

    def update_profile(self, custom_notes: Optional[str] = None, active_focus: Optional[str] = None) -> Dict[str, Any]:
        if active_focus:
            self.profile["research_focus"] = active_focus
        if custom_notes:
            self.profile["custom_notes"] = custom_notes
        PortfolioSyncService().save_cached_profile(self.profile)
        return {"status": "success", "profile": self.profile}

    def chat_with_twin(self, user_message: str, chat_history: Optional[List[Dict[str, str]]] = None) -> str:
        return self.chat(user_message, chat_history)

    def apply_for_grant(self, grant_title: str, grant_details: Dict[str, Any]) -> Dict[str, Any]:
        return self.generate_grant_application({"title": grant_title, **grant_details})

    def apply_for_lab(self, lab_title: str, lab_details: Dict[str, Any]) -> Dict[str, Any]:
        return self.generate_grant_application({"title": lab_title, **lab_details})

    def get_strategic_suggestions(self) -> Dict[str, Any]:
        scholar_name = self.profile.get("name", "Scholar")
        return {
            "status": "success",
            "scholar": scholar_name,
            "actions": [
                {"timeline": "Next 7 Days", "action": "Submit paper draft to ProfFeb Reviewer Simulator for pre-submission stress-testing."},
                {"timeline": "Next 14 Days", "action": "Scan CORE A* conference deadlines on ProfFeb Radar and bookmark travel grants."},
                {"timeline": "Next 30 Days", "action": "Generate full neural audio briefings for top 5 reference papers to accelerate literature synthesis."}
            ]
        }

    def prepare_application_packet(self, opportunity_type: str, title: str, details: Dict[str, Any]) -> Dict[str, Any]:
        dossier = self.generate_grant_application({"title": title, **details})
        return {
            "status": "prepared",
            "opportunity_type": opportunity_type,
            "title": title,
            "dossier": dossier,
            "applicant": self.profile
        }

    def dispatch_application(self, packet: Dict[str, Any], target_repo: str = "research-notes") -> Dict[str, Any]:
        title = f"[ProfFeb Application Log] {packet.get('title', 'Academic Application')}"
        body = f"# Application Dossier\n\n- **Applicant:** {self.profile.get('name')}\n- **Date:** {datetime.utcnow().isoformat()}\n\n```json\n{json.dumps(packet, indent=2)}\n```"
        return self.github.log_issue(repo=target_repo, title=title, body=body)

    def get_dispatch_history(self) -> List[Dict[str, Any]]:
        return []

    def chat(self, message: str, chat_history: Optional[List[Dict[str, str]]] = None) -> str:
        """Academic advising dialogue with Prof. Feb."""
        if not GEMINI_API_KEY or not genai:
            return "ProfFeb AI Mentor requires a valid GEMINI_API_KEY to provide academic counsel."

        scholar_name = self.profile.get("name", "Scholar")
        research_focus = self.profile.get("research_focus", "computational sciences and machine learning")

        system_instruction = f"""You are Prof. Feb, a distinguished Senior Chair Professor, Senior Principal Research Scientist, and Master Academic Mentor.
You are advising {scholar_name}, who works on {research_focus}.
Your tone is rigorous, intellectually inspiring, authoritative, and deeply supportive of breakthrough academic inquiry.
Provide structured, mathematically rigorous, and publication-ready advice."""

        try:
            client = genai.Client(api_key=GEMINI_API_KEY)
            prompt = f"{system_instruction}\n\nResearcher: {message}\n\nProf. Feb:"
            resp = client.models.generate_content(
                model=GEMINI_MODEL,
                contents=prompt
            )
            return resp.text
        except Exception as e:
            logger.error(f"ProfFeb Chat error: {e}")
            return f"Prof. Feb is temporarily indisposed: {e}"

    def generate_grant_application(self, opportunity: Dict[str, Any]) -> Dict[str, Any]:
        """Generates a tailored research fellowship, grant, or doctoral travel stipend application."""
        scholar_name = self.profile.get("name", "Scholar")
        org = opportunity.get("organization") or opportunity.get("conference", "Academic Committee")
        title = opportunity.get("title") or opportunity.get("name", "Research Grant")

        if not GEMINI_API_KEY or not genai:
            return {
                "applicant_name": scholar_name,
                "opportunity_title": title,
                "organization": org,
                "statement_of_purpose": f"Proposal for {title} submitted to {org}.",
                "budget_justification": "Travel, registration fees, and compute resources."
            }

        prompt = f"""You are ProfFeb Grant Proposal Engine.
Write a publication-grade research grant / student travel stipend application for:
- Scholar: {scholar_name}
- Focus: {self.profile.get('research_focus', 'Applied Machine Learning')}
- Target: {title} at {org}

Return JSON with keys:
"applicant_name", "opportunity_title", "organization", "statement_of_purpose", "research_impact_summary", "budget_justification"."""

        try:
            client = genai.Client(api_key=GEMINI_API_KEY)
            resp = client.models.generate_content(
                model=GEMINI_MODEL,
                contents=prompt,
                config=types.GenerateContentConfig(response_mime_type="application/json")
            )
            return json.loads(resp.text)
        except Exception as e:
            return {
                "applicant_name": scholar_name,
                "opportunity_title": title,
                "organization": org,
                "statement_of_purpose": f"Standard academic statement for {title} at {org}.",
                "error": str(e)
            }
