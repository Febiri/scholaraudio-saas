-- ==============================================================================
-- ProfFeb — Global SaaS Database Schema & Supabase Configuration
-- Multi-Tenant Architecture with Row-Level Security (RLS)
-- ==============================================================================

-- 1. Create Profiles Table (Linked to Supabase auth.users)
CREATE TABLE IF NOT EXISTS public.profiles (
    id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    email TEXT,
    full_name TEXT,
    institution TEXT,
    research_field TEXT,
    tier TEXT DEFAULT 'scholar', -- 'scholar' (free), 'fellow' ($9/mo), 'lab' ($29/mo)
    zotero_user_id TEXT,
    zotero_api_key TEXT,
    preferred_voice TEXT DEFAULT 'en-NG-AbeoNeural',
    created_at TIMESTAMPTZ DEFAULT TIMEZONE('utc'::text, NOW()) NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT TIMEZONE('utc'::text, NOW()) NOT NULL
);

-- 2. Create Papers Table (Scoped to user_id)
CREATE TABLE IF NOT EXISTS public.papers (
    id BIGSERIAL PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    zotero_item_key VARCHAR(64),
    title VARCHAR(512) NOT NULL,
    authors VARCHAR(512) DEFAULT '',
    abstract TEXT DEFAULT '',
    publication_year VARCHAR(32) DEFAULT '',
    journal VARCHAR(256) DEFAULT '',
    pdf_path VARCHAR(512),
    has_pdf BOOLEAN DEFAULT FALSE,
    summary_text TEXT,
    summary_problem TEXT,
    summary_methodology TEXT,
    summary_results TEXT,
    summary_limitations TEXT,
    full_text TEXT,
    audio_mode VARCHAR(32) DEFAULT 'summary',
    audio_path VARCHAR(512),
    audio_duration FLOAT DEFAULT 0.0,
    summary_audio_path VARCHAR(512),
    summary_audio_duration FLOAT DEFAULT 0.0,
    full_audio_path VARCHAR(512),
    full_audio_duration FLOAT DEFAULT 0.0,
    voice_used VARCHAR(64) DEFAULT 'en-NG-AbeoNeural',
    status VARCHAR(32) DEFAULT 'Pending',
    error_message TEXT,
    created_at TIMESTAMPTZ DEFAULT TIMEZONE('utc'::text, NOW()) NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT TIMEZONE('utc'::text, NOW()) NOT NULL
);

-- 3. Create Notes Table (Annotations, critiques, and theoretical links)
CREATE TABLE IF NOT EXISTS public.notes (
    id BIGSERIAL PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    paper_id BIGINT REFERENCES public.papers(id) ON DELETE CASCADE,
    content TEXT NOT NULL,
    tags TEXT,
    created_at TIMESTAMPTZ DEFAULT TIMEZONE('utc'::text, NOW()) NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT TIMEZONE('utc'::text, NOW()) NOT NULL
);

-- 4. Create Conference Watchlists Table
CREATE TABLE IF NOT EXISTS public.conference_watchlists (
    id BIGSERIAL PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    conference_name TEXT NOT NULL,
    acronym TEXT,
    core_rank TEXT,
    submission_deadline TEXT,
    location TEXT,
    travel_grant TEXT,
    notes TEXT,
    created_at TIMESTAMPTZ DEFAULT TIMEZONE('utc'::text, NOW()) NOT NULL
);

-- ==============================================================================
-- 5. Row-Level Security (RLS) Policies
-- Ensures complete air-gap and multi-tenant data isolation between users
-- ==============================================================================

-- Enable RLS on all tables
ALTER TABLE public.profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.papers ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.notes ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.conference_watchlists ENABLE ROW LEVEL SECURITY;

-- Profiles Policies
CREATE POLICY "Users can view own profile"
    ON public.profiles FOR SELECT
    USING (auth.uid() = id);

CREATE POLICY "Users can update own profile"
    ON public.profiles FOR UPDATE
    USING (auth.uid() = id);

CREATE POLICY "Users can insert own profile"
    ON public.profiles FOR INSERT
    WITH CHECK (auth.uid() = id);

-- Papers Policies
CREATE POLICY "Users can view own papers"
    ON public.papers FOR SELECT
    USING (auth.uid() = user_id);

CREATE POLICY "Users can insert own papers"
    ON public.papers FOR INSERT
    WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can update own papers"
    ON public.papers FOR UPDATE
    USING (auth.uid() = user_id);

CREATE POLICY "Users can delete own papers"
    ON public.papers FOR DELETE
    USING (auth.uid() = user_id);

-- Notes Policies
CREATE POLICY "Users can view own notes"
    ON public.notes FOR SELECT
    USING (auth.uid() = user_id);

CREATE POLICY "Users can insert own notes"
    ON public.notes FOR INSERT
    WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can update own notes"
    ON public.notes FOR UPDATE
    USING (auth.uid() = user_id);

CREATE POLICY "Users can delete own notes"
    ON public.notes FOR DELETE
    USING (auth.uid() = user_id);

-- Watchlist Policies
CREATE POLICY "Users can view own watchlist"
    ON public.conference_watchlists FOR SELECT
    USING (auth.uid() = user_id);

CREATE POLICY "Users can insert into own watchlist"
    ON public.conference_watchlists FOR INSERT
    WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can delete from own watchlist"
    ON public.conference_watchlists FOR DELETE
    USING (auth.uid() = user_id);

-- ==============================================================================
-- 6. Trigger: Auto-create Profile on Supabase User Sign Up
-- ==============================================================================
CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS TRIGGER AS $$
BEGIN
    INSERT INTO public.profiles (id, email, full_name, tier)
    VALUES (
        new.id,
        new.email,
        COALESCE(new.raw_user_meta_data->>'full_name', split_part(new.email, '@', 1)),
        'scholar'
    )
    ON CONFLICT (id) DO NOTHING;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Recreate trigger cleanly
DROP TRIGGER IF EXISTS on_auth_user_created ON auth.users;
CREATE TRIGGER on_auth_user_created
    AFTER INSERT ON auth.users
    FOR EACH ROW EXECUTE FUNCTION public.handle_new_user();

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_papers_user_id ON public.papers(user_id);
CREATE INDEX IF NOT EXISTS idx_notes_user_id ON public.notes(user_id);
CREATE INDEX IF NOT EXISTS idx_notes_paper_id ON public.notes(paper_id);
CREATE INDEX IF NOT EXISTS idx_watchlists_user_id ON public.conference_watchlists(user_id);
