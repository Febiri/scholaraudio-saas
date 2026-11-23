# 🎓 ProfFeb — Neural Audio Research Workstation & AI Academic Copilot

[![License: MIT](https://img.shields.io/badge/License-MIT-emerald.svg)](LICENSE)
[![FastAPI](https://img.shields.io/badge/Backend-FastAPI-009688.svg)](https://fastapi.tiangolo.com/)
[![Supabase](https://img.shields.io/badge/Auth%20%26%20Database-Supabase%20PostgreSQL-3ECF8E.svg)](https://supabase.com/)
[![Gemini Flash](https://img.shields.io/badge/LLM-Gemini%202.5%20Flash-4285F4.svg)](https://deepmind.google/technologies/gemini/)
[![Edge-TTS](https://img.shields.io/badge/Audio-Edge--TTS%20Neural-blue.svg)](https://github.com/rany2/edge-tts)

**ProfFeb** is a high-performance, multi-tenant AI academic workstation designed for global doctoral researchers, professors, and scholarly labs. It transforms academic paper consumption through multimodal neural audio narration, phonetic mathematical deconstruction, figure extraction, conference scouting, simulated peer reviews, research idea novelty auditing, and an autonomous Academic Co-Pilot.

---

## 🏛️ Platform Architecture & 7 Intelligence Engines

```
                                      🌐 PROFFEB GLOBAL SAAS
                                               (/)
                                                │
         ┌───────────────────┬──────────────────┼──────────────────┬──────────────────┐
         ▼                   ▼                  ▼                  ▼                  ▼
  [ Engine 01 ]       [ Engine 02 ]      [ Engine 03 ]      [ Engine 04 ]      [ Engine 05-07 ]
  📖 Research Studio  🌐 Event Scout     🛰️ Research Radar  ⚖️ Peer Reviewer    💰 Grants (/grants)
  (/app)              (/conferences)     (/radar)           (/reviewer)        🔬 Labs (/lab-connector)
  • Verbatim Audio    • CORE Rankings    • Novelty scoring  • Rigor scoring    🎓 Co-Pilot (/agent)
  • 4-Part Briefings  • PhD consortiums  • Literature gaps  • Camera-ready     • Thesis tracking
  • Math phonetics    • Travel grants    • Pivot roadmap      rubric audits    • Dispatched briefs
```

### 1. 📖 Spoken Research Studio & Paper Reader (`/app`)
* **100% Verbatim Full-Paper Narration**: Complete mathematical derivations and citations without skipping.
* **4-Part Senior Mentor Briefings**:
  1. 🎯 *Theoretical Foundations & Problem Formulation*
  2. 🔬 *Methodological Framework & Architecture*
  3. 📊 *Empirical Results, Benchmarks & Statistical Proofs*
  4. ⚠️ *Critical Limitations, Theoretical Bounds & Future Horizons*
* **Phonetic Mathematical Normalizer**: Vocalizes complex LaTeX equations, Greek symbols ($\alpha, \beta, \theta$), integrations ($\int$), and statistical metrics ($p < 0.001$, $R^2$) for auditory clarity.
* **Extracted Visuals & Interactive Player**: Real-time paragraph synchronization, in-document figure inspection, and chapter seeking.
* **Global Voices**: Natural West African neural speech (Ghanaian Abeo & Ezinne), plus East African, South African, and international scholarly accents.

### 2. 🌐 Intelligent Conference & Event Scout (`/conferences`)
* **Global Academic Discovery**: Scans international academic registries, CORE A*/A rankings, IEEE, ACM, and computational venues.
* **Doctoral Opportunities**: Pinpoint Doctoral Consortiums, thesis mentoring workshops, and student travel grants with live countdown badges.
* **Personalized Watchlist**: Save upcoming conferences to track deadlines and export key dates to your academic calendar.

### 3. 🛰️ Research Radar & Idea Validator (`/radar`)
* **Novelty & Feasibility Auditing**: Stress-tests paper ideas against the latest state of the art to prevent reinventing existing literature.
* **Risk Analysis & Pivot Roadmap**: Highlights methodological pitfalls before submitting to top-tier conferences.

### 4. ⚖️ Virtual Peer Reviewer & Paper Auditor (`/reviewer`)
* **Simulated Program Committee Review**: Simulates strict NeurIPS/ICLR/IEEE reviewer committees with 5-score criteria (Soundness, Novelty, Presentation, Empirical Rigor).
* **Direct PDF Upload**: Audits manuscript PDFs and highlights actionable camera-ready revisions.

### 5. 💰 Global Grant & Fellowship Finder (`/grants`)
* Curated research funding, post-doctoral fellowships, and equipment grants across NSF, ERC, and private foundations.

### 6. 🔬 Lab Connector & Collaborative Network (`/lab-connector`)
* Matches research groups, finding complementary labs and potential academic co-authors across international institutions.

### 7. 🎓 Academic Co-Pilot & Research Digital Twin (`/agent`)
* **Autonomous Scholar Assistant**: Tracks research deliverables, drafts dissertation chapters, summarizes daily ArXiv trends, and dispatches weekly briefings.

---

## 🔒 Security & Multi-Tenant Database Architecture

ProfFeb is architected for enterprise multi-tenancy and data isolation:

* **Authentication**: Supabase Auth supporting Google OAuth 2.0, Magic Links, and Email/Password.
* **Row-Level Security (RLS)**: Enforced directly at the PostgreSQL layer via `auth.uid()`.
  * `public.profiles`: User tier, institution, and voice preferences.
  * `public.papers`: Scoped strictly to `user_id = auth.uid()`.
  * `public.notes`: User annotations and paper takeaways scoped to `user_id`.
  * `public.conference_watchlists`: Personal conference tracking.
* **Hybrid Storage Support**: Seamlessly falls back to local SQLite with dynamic schema migration during offline or test environments.

---

## 🛠️ Technology Stack

| Layer | Technologies |
|---|---|
| **Backend** | Python 3.10+, FastAPI, Uvicorn, SQLAlchemy |
| **Authentication & DB** | Supabase Auth, PostgreSQL with Row-Level Security (RLS) |
| **Artificial Intelligence** | Google GenAI SDK (`google-genai`), Gemini 2.5 Flash |
| **Neural Speech Engine** | Microsoft Edge-TTS (Zero-cost neural audio synthesis) |
| **PDF Extraction** | PyMuPDF (`fitz`) with vector figure extraction |
| **Frontend** | Modern glassmorphic responsive UI, Tailwind CSS, KaTeX, Marked.js |

---

## 🚀 Getting Started

### 1. Clone the Repository
```bash
git clone https://github.com/Febiri/scholaraudio-saas.git
cd scholaraudio-saas
```

### 2. Set Up Virtual Environment & Dependencies
```bash
python -m venv venv

# On Windows:
.\venv\Scripts\activate

# On macOS/Linux:
source venv/bin/activate

pip install -r requirements.txt
```

### 3. Configure Environment Variables
Copy `.env.example` to `.env`:
```bash
cp .env.example .env
```

Set your configuration keys:
```env
# Application Brand
APP_NAME=ProfFeb
APP_TAGLINE="Neural Research Briefings & Multi-Modal Academic Workstation"

# AI Engine
GEMINI_API_KEY=your_google_gemini_api_key
GEMINI_MODEL=gemini-2.5-flash

# Supabase Multi-Tenant SaaS
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your_supabase_anon_public_key
SUPABASE_SERVICE_ROLE_KEY=your_service_role_key_optional

# Audio Preferences
DEFAULT_TTS_VOICE=en-NG-AbeoNeural
```

### 4. Apply Database Migrations (Supabase)
Run the queries in `supabase_schema.sql` directly inside your **Supabase SQL Editor** to establish the multi-tenant tables, trigger functions, and Row-Level Security policies.

### 5. Run the SaaS Server
```bash
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload
```

Navigate to:
* **Landing Page:** [http://127.0.0.1:8000/](http://127.0.0.1:8000/)
* **Research Studio:** [http://127.0.0.1:8000/app](http://127.0.0.1:8000/app)
* **Conference Scout:** [http://127.0.0.1:8000/conferences](http://127.0.0.1:8000/conferences)
* **Academic Co-Pilot:** [http://127.0.0.1:8000/agent](http://127.0.0.1:8000/agent)
* **API Documentation:** [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)

---

## 🧪 Testing & Verification

Run the comprehensive SaaS automated test suite:
```bash
python tests/test_pdf_engines.py
```
This tests:
1. All public HTML frontend routes.
2. Configuration & Supabase public keys (`/api/config`).
3. Authentication session verification (`/api/auth/me`).
4. Peer Reviewer simulation (`/api/reviewer/simulate`).
5. Research Radar idea auditing (`/api/radar/analyze`).
6. PDF upload & PyMuPDF extraction.
7. Conference watchlist CRUD.
8. Academic Co-Pilot profile endpoints.
9. System health check (`/api/health`).

---

## 📄 License
This project is licensed under the [MIT License](LICENSE).
