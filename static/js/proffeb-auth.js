/**
 * ProfFeb — Global SaaS Authentication, Session & Scholar Profile Manager
 * Powered by Supabase Auth with Google OAuth, Email/Password & Profile Engine
 */

(function () {
  'use strict';

  // Transparent fetch interceptor: attaches Bearer token to /api/ requests when signed in
  if (!window._proffebFetchIntercepted) {
    window._proffebFetchIntercepted = true;
    const rawFetch = window.fetch;
    window.fetch = function (input, init = {}) {
      const url = typeof input === 'string' ? input : (input && input.url ? input.url : '');
      if (window.ProfFebAuth && window.ProfFebAuth.token && url.startsWith('/api/')) {
        init = Object.assign({}, init);
        if (init.headers instanceof Headers) {
          if (!init.headers.has('Authorization')) {
            init.headers.set('Authorization', `Bearer ${window.ProfFebAuth.token}`);
          }
        } else if (Array.isArray(init.headers)) {
          if (!init.headers.some(([k]) => k.toLowerCase() === 'authorization')) {
            init.headers.push(['Authorization', `Bearer ${window.ProfFebAuth.token}`]);
          }
        } else {
          init.headers = Object.assign({}, init.headers);
          if (!init.headers['Authorization'] && !init.headers['authorization']) {
            init.headers['Authorization'] = `Bearer ${window.ProfFebAuth.token}`;
          }
        }
      }
      return rawFetch.call(this, input, init);
    };
  }

  window.ProfFebAuth = {
    supabase: null,
    currentUser: null,
    token: null,
    config: null,
    profile: null,
    stats: { papers_synced: 0, audio_minutes: 0, watchlist_count: 0 },
    currentMode: 'signin',
    _audioPreview: null,

    getAuthHeaders() {
      if (this.token) {
        return { 'Authorization': `Bearer ${this.token}` };
      }
      return {};
    },

    async init() {
      try {
        // 1. Fetch public platform config from backend
        const res = await fetch('/api/config');
        if (!res.ok) throw new Error('Could not load platform config');
        this.config = await res.json();

        // 2. Initialize Supabase Client
        const anonKey = this.config.supabase_anon_key || this.config.supabase_key;
        if (window.supabase && this.config.supabase_url && anonKey) {
          this.supabase = window.supabase.createClient(
            this.config.supabase_url,
            anonKey
          );

          // Check current active session
          const { data: { session } } = await this.supabase.auth.getSession();
          if (session) {
            this.currentUser = session.user;
            this.token = session.access_token;
            this.loadUserProfile();
          }

          // Clean Google OAuth hash fragments (#access_token=...) from URL
          this.cleanOAuthUrlHash();

          // Listen for reactive auth changes (Sign In, Sign Out, OAuth Return, Token Refresh)
          this.supabase.auth.onAuthStateChange(async (event, session) => {
            if (session) {
              const isFirstLogin = !this.currentUser && (event === 'SIGNED_IN');
              this.currentUser = session.user;
              this.token = session.access_token;
              this.cleanOAuthUrlHash();
              await this.loadUserProfile();
              this.renderNavbarUI();

              if (isFirstLogin) {
                const name = this.profile?.full_name || this.currentUser.user_metadata?.full_name || 'Scholar';
                if (window.ProfFebUI && ProfFebUI.toast) {
                  ProfFebUI.toast({
                    title: `Welcome, ${name}!`,
                    message: 'Your neural research workspace is ready.',
                    type: 'success',
                    duration: 4000
                  });
                }
                // If profile is missing academic affiliation, open profile modal after slight delay
                if (!this.profile?.institution && !this.profile?.research_field) {
                  setTimeout(() => this.openProfileModal(), 1200);
                }
              }
            } else {
              this.currentUser = null;
              this.token = null;
              this.profile = null;
              this.renderNavbarUI();
            }

            window.dispatchEvent(new CustomEvent('proffeb-auth-changed', {
              detail: { user: this.currentUser, token: this.token, profile: this.profile }
            }));
          });
        }
      } catch (err) {
        console.warn('ProfFeb Auth initialization note:', err);
      }

      this.injectAuthModal();
      this.injectProfileModal();
      this.renderNavbarUI();
    },

    cleanOAuthUrlHash() {
      if (window.location.hash && (window.location.hash.includes('access_token=') || window.location.hash.includes('error='))) {
        try {
          window.history.replaceState(null, document.title, window.location.pathname + window.location.search);
        } catch (e) {}
      }
    },

    async loadUserProfile() {
      if (!this.currentUser) return null;
      try {
        const res = await this.fetchWithAuth('/api/user/profile');
        if (res.ok) {
          const data = await res.json();
          if (data && data.user) {
            this.profile = data.user;
            if (data.stats) this.stats = data.stats;
            this.renderNavbarUI();
            this.populateProfileModal();
            return data;
          }
        }
      } catch (e) {
        console.warn('Could not load user academic profile:', e);
      }
      return null;
    },

    async fetchWithAuth(url, options = {}) {
      options.headers = options.headers || {};
      if (this.token) {
        if (options.headers instanceof Headers) {
          options.headers.set('Authorization', `Bearer ${this.token}`);
        } else {
          options.headers['Authorization'] = `Bearer ${this.token}`;
        }
      }
      return fetch(url, options);
    },

    async clearCache() {
      try {
        localStorage.clear();
        sessionStorage.clear();
        await fetch('/api/admin/clear-cache', { method: 'POST' });
      } catch (e) {}
      if (window.ProfFebUI && ProfFebUI.toast) {
        ProfFebUI.toast({
          title: 'Cache Cleared',
          message: 'Local session cleared. Reloading workstation...',
          type: 'info'
        });
      }
      setTimeout(() => window.location.reload(), 600);
    },

    renderNavbarUI() {
      const container = document.getElementById('user-nav-container');
      if (!container) return;

      if (this.currentUser) {
        const meta = this.currentUser.user_metadata || {};
        const name = this.profile?.full_name || meta.full_name || meta.name || this.currentUser.email.split('@')[0];
        const initials = (name || 'U').slice(0, 2).toUpperCase();
        const avatarUrl = this.profile?.avatar_url || meta.avatar_url || meta.picture || '';
        const tier = (this.profile?.tier || meta.tier || 'Scholar').toUpperCase();
        const academicTitle = this.profile?.academic_title || meta.academic_title || 'Scholar';

        const avatarMarkup = avatarUrl
          ? `<img src="${avatarUrl}" alt="${name}" style="width:26px;height:26px;border-radius:8px;object-fit:cover;border:1px solid var(--pf-border-subtle);" onerror="this.outerHTML='<div style=\'width:26px;height:26px;border-radius:8px;background:linear-gradient(135deg,var(--pf-primary),var(--pf-accent-scout));color:#fff;display:flex;align-items:center;justify-content:center;font-weight:700;font-size:11px;\'>${initials}</div>'">`
          : `<div style="width:26px;height:26px;border-radius:8px;background:linear-gradient(135deg,var(--pf-primary),var(--pf-accent-scout));color:#fff;display:flex;align-items:center;justify-content:center;font-weight:700;font-size:11px;">${initials}</div>`;

        container.innerHTML = `
          <div class="relative inline-block text-left" id="user-menu-root">
            <button id="user-menu-btn" type="button" class="pf-btn pf-btn-secondary pf-btn-sm" style="display:flex;align-items:center;gap:8px;padding:3px 10px 3px 5px;border-radius:12px;" aria-label="User Menu">
              ${avatarMarkup}
              <div class="text-left hidden sm:block" style="text-align:left;">
                <div style="font-size:12px;font-weight:600;color:var(--pf-text-primary);line-height:1.2;max-width:115px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${name}</div>
                <div style="display:flex;align-items:center;gap:4px;">
                  <span style="font-size:9px;font-family:var(--pf-font-mono);font-weight:700;color:var(--pf-primary);text-transform:uppercase;">${tier}</span>
                  <span style="font-size:9px;color:var(--pf-text-muted);">• ${academicTitle.split(' ')[0]}</span>
                </div>
              </div>
              <i data-lucide="chevron-down" style="width:13px;height:13px;color:var(--pf-text-muted);"></i>
            </button>

            <!-- Dropdown Menu -->
            <div id="user-menu-dropdown" class="hidden absolute right-0 mt-2 w-72 rounded-2xl py-2 z-50 animate-in fade-in zoom-in-95 duration-100" style="background:var(--pf-bg-surface-elevated);border:1px solid var(--pf-border-subtle);color:var(--pf-text-primary);box-shadow:var(--pf-shadow-xl);">
              <!-- User Overview Card -->
              <div class="px-4 py-3 border-b" style="border-color:var(--pf-border-subtle);background:var(--pf-bg-surface-subtle);border-top-left-radius:15px;border-top-right-radius:15px;">
                <div style="display:flex;align-items:center;gap:10px;">
                  ${avatarMarkup}
                  <div style="flex:1;min-width:0;">
                    <div style="font-size:13px;font-weight:700;color:var(--pf-text-primary);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${name}</div>
                    <div style="font-size:11px;color:var(--pf-text-muted);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${this.currentUser.email}</div>
                  </div>
                </div>
                <div style="display:flex;align-items:center;justify-content:space-between;margin-top:8px;padding-top:6px;border-top:1px dashed var(--pf-border-subtle);">
                  <span style="font-size:10px;font-weight:700;color:var(--pf-success);background:var(--pf-accent-copilot-subtle);padding:2px 8px;border-radius:999px;">✓ Active ${tier}</span>
                  <span style="font-size:10px;color:var(--pf-text-muted);font-family:var(--pf-font-mono);">${this.stats.papers_synced || 0} papers</span>
                </div>
              </div>

              <!-- Academic Profile Action Button -->
              <div class="p-2">
                <button type="button" onclick="ProfFebAuth.openProfileModal()" class="w-full text-left flex items-center gap-2.5 px-3 py-2.5 rounded-xl text-xs font-bold transition hover:bg-slate-100 dark:hover:bg-slate-800" style="color:var(--pf-primary);background:var(--pf-accent-studio-subtle);border:1px solid rgba(37,99,235,0.15);cursor:pointer;">
                  <i data-lucide="user-check" style="width:16px;height:16px;color:var(--pf-primary);"></i>
                  <div style="flex:1;">
                    <div>Academic Profile & Credentials</div>
                    <div style="font-size:10px;font-weight:400;color:var(--pf-text-secondary);">Manage affiliation, field & neural voice</div>
                  </div>
                </button>
              </div>

              <div class="px-2 py-1">
                <a href="/app" class="flex items-center gap-2.5 px-3 py-2 text-xs font-medium rounded-lg transition hover:bg-slate-100 dark:hover:bg-slate-800" style="color:var(--pf-text-secondary);text-decoration:none;">
                  <i data-lucide="headphones" style="width:14px;height:14px;color:var(--pf-engine-studio);"></i> Research Studio
                </a>
                <a href="/conferences" class="flex items-center gap-2.5 px-3 py-2 text-xs font-medium rounded-lg transition hover:bg-slate-100 dark:hover:bg-slate-800" style="color:var(--pf-text-secondary);text-decoration:none;">
                  <i data-lucide="calendar" style="width:14px;height:14px;color:var(--pf-engine-scout);"></i> Conference Scout
                </a>
                <a href="/agent" class="flex items-center gap-2.5 px-3 py-2 text-xs font-medium rounded-lg transition hover:bg-slate-100 dark:hover:bg-slate-800" style="color:var(--pf-text-secondary);text-decoration:none;">
                  <i data-lucide="bot" style="width:14px;height:14px;color:var(--pf-engine-copilot);"></i> Academic Co-Pilot
                </a>
              </div>

              <div class="border-t my-1" style="border-color:var(--pf-border-subtle);"></div>

              <div class="px-2 py-1">
                <button type="button" onclick="if(window.ProfFebUI&&ProfFebUI.zotero)ProfFebUI.zotero.open()" class="w-full text-left flex items-center gap-2.5 px-3 py-2 text-xs font-medium rounded-lg transition hover:bg-slate-100 dark:hover:bg-slate-800" style="color:var(--pf-text-secondary);background:transparent;border:none;cursor:pointer;">
                  <i data-lucide="library" style="width:14px;height:14px;color:var(--pf-primary);"></i> Zotero Library Setup
                </button>
                <button type="button" onclick="if(window.ProfFebUI&&ProfFebUI.settings)ProfFebUI.settings.open()" class="w-full text-left flex items-center gap-2.5 px-3 py-2 text-xs font-medium rounded-lg transition hover:bg-slate-100 dark:hover:bg-slate-800" style="color:var(--pf-text-secondary);background:transparent;border:none;cursor:pointer;">
                  <i data-lucide="settings" style="width:14px;height:14px;color:var(--pf-text-muted);"></i> Workstation Settings
                </button>
                <button type="button" onclick="ProfFebAuth.clearCache()" class="w-full text-left flex items-center gap-2.5 px-3 py-2 text-xs font-medium rounded-lg transition hover:bg-slate-100 dark:hover:bg-slate-800" style="color:var(--pf-text-muted);background:transparent;border:none;cursor:pointer;">
                  <i data-lucide="refresh-cw" style="width:14px;height:14px;color:var(--pf-text-muted);"></i> Clear Cache & Reload
                </button>
              </div>

              <div class="border-t my-1" style="border-color:var(--pf-border-subtle);"></div>

              <div class="px-2 pt-1 pb-1">
                <button type="button" onclick="ProfFebAuth.signOut()" class="w-full text-left flex items-center gap-2.5 px-3 py-2 text-xs font-semibold rounded-lg transition hover:bg-red-50 dark:hover:bg-red-950/30" style="color:var(--pf-danger);background:transparent;border:none;cursor:pointer;">
                  <i data-lucide="log-out" style="width:14px;height:14px;color:var(--pf-danger);"></i> Sign Out of ProfFeb
                </button>
              </div>
            </div>
          </div>
        `;

        const btn = document.getElementById('user-menu-btn');
        const dropdown = document.getElementById('user-menu-dropdown');
        if (btn && dropdown) {
          btn.addEventListener('click', (e) => {
            e.stopPropagation();
            dropdown.classList.toggle('hidden');
          });
          document.addEventListener('click', () => dropdown.classList.add('hidden'));
        }
      } else {
        container.innerHTML = `
          <div class="flex items-center gap-2">
            <button type="button" onclick="ProfFebAuth.openModal('signin')" class="pf-btn pf-btn-ghost pf-btn-sm" style="font-weight:600;font-size:13px;padding:6px 12px;border:1px solid var(--pf-border-subtle);">
              Sign In
            </button>
            <button type="button" onclick="ProfFebAuth.openModal('signup')" class="pf-btn pf-btn-primary pf-btn-sm shadow-xs" style="font-weight:600;font-size:13px;display:flex;align-items:center;gap:6px;padding:6px 14px;">
              <span>Get Started</span>
              <i data-lucide="arrow-right" style="width:13px;height:13px;"></i>
            </button>
          </div>
        `;
      }

      if (window.lucide && typeof window.lucide.createIcons === 'function') {
        window.lucide.createIcons();
      }
    },

    // -------------------------------------------------------------
    // SIGN IN & SIGN UP MODAL
    // -------------------------------------------------------------
    injectAuthModal() {
      if (document.getElementById('proffeb-auth-modal-overlay')) return;

      const modalHtml = `
        <div id="proffeb-auth-modal-overlay" class="pf-modal-overlay" style="z-index: 1000;">
          <div class="pf-modal" style="max-width: 440px; border-radius: 24px; box-shadow: var(--pf-shadow-2xl); background: var(--pf-bg-surface-elevated);">
            <!-- Modal Header -->
            <div style="padding: 1.25rem 1.5rem 1rem; display: flex; align-items: center; justify-content: space-between; border-bottom: 1px solid var(--pf-border-subtle);">
              <div style="display: flex; align-items: center;">
                <img src="/static/brand/proffeb-logo.svg" alt="ProfFeb" class="pf-logo-img pf-logo-light" style="height: 32px; width: auto;" />
                <img src="/static/brand/proffeb-logo-dark.svg" alt="ProfFeb" class="pf-logo-img pf-logo-dark" style="height: 32px; width: auto;" />
              </div>
              <button type="button" onclick="ProfFebAuth.closeModal()" class="pf-btn pf-btn-ghost pf-btn-sm" style="border-radius: 50%; width: 28px; height: 28px; padding: 0; display: flex; align-items: center; justify-content: center; color: var(--pf-text-muted);" aria-label="Close">
                ✕
              </button>
            </div>

            <!-- Tab Switcher -->
            <div style="display: flex; background: var(--pf-bg-surface-subtle); padding: 4px; border-bottom: 1px solid var(--pf-border-subtle);">
              <button id="tab-auth-signin" type="button" onclick="ProfFebAuth.switchTab('signin')" style="flex: 1; padding: 8px 12px; font-size: 12px; font-weight: 700; border-radius: 10px; border: none; cursor: pointer; transition: var(--pf-transition); background: var(--pf-bg-surface); color: var(--pf-primary); box-shadow: var(--pf-shadow-xs);">
                Sign In
              </button>
              <button id="tab-auth-signup" type="button" onclick="ProfFebAuth.switchTab('signup')" style="flex: 1; padding: 8px 12px; font-size: 12px; font-weight: 600; border-radius: 10px; border: none; cursor: pointer; transition: var(--pf-transition); background: transparent; color: var(--pf-text-secondary);">
                Create Account
              </button>
            </div>

            <div style="padding: 1.5rem;">
              <!-- One-Click Google OAuth -->
              <button id="btn-google-oauth" onclick="ProfFebAuth.signInWithGoogle()" type="button" class="pf-btn pf-btn-secondary" style="width: 100%; display: flex; align-items: center; justify-content: center; gap: 10px; padding: 10px 16px; border-radius: 12px; font-size: 13px; font-weight: 600;">
                <svg style="width: 18px; height: 18px;" viewBox="0 0 24 24">
                  <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"/>
                  <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/>
                  <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.06H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.94l2.85-2.22.81-.63z"/>
                  <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.06l3.66 2.84c.87-2.6 3.3-4.52 6.16-4.52z"/>
                </svg>
                <span id="btn-google-label">Continue with Google</span>
              </button>

              <div style="position: relative; margin: 1.25rem 0; text-align: center;">
                <div style="position: absolute; inset: 0; display: flex; align-items: center;"><div style="width: 100%; border-top: 1px solid var(--pf-border-subtle);"></div></div>
                <span style="position: relative; background: var(--pf-bg-surface-elevated); padding: 0 10px; font-size: 10px; text-transform: uppercase; font-family: var(--pf-font-mono); letter-spacing: 0.05em; color: var(--pf-text-muted);">
                  or with academic email
                </span>
              </div>

              <!-- Alerts -->
              <div id="auth-alert-box" style="display: none; margin-bottom: 1rem; padding: 10px 14px; border-radius: 12px; font-size: 12px; font-weight: 500;"></div>

              <!-- Main Form -->
              <form id="proffeb-auth-form" onsubmit="ProfFebAuth.handleFormSubmit(event)" style="display: flex; flex-direction: column; gap: 12px;">
                <div id="field-auth-fullname" style="display: none;">
                  <label style="display: block; font-size: 11px; font-weight: 600; color: var(--pf-text-primary); margin-bottom: 4px;">Full Name</label>
                  <input id="auth-fullname" type="text" placeholder="e.g. Dr. Jane Smith" class="pf-input" style="width: 100%; box-sizing: border-box; font-size: 13px; padding: 8px 12px; border-radius: 10px; border: 1px solid var(--pf-border-default); background: var(--pf-bg-surface);">
                </div>

                <div>
                  <label style="display: block; font-size: 11px; font-weight: 600; color: var(--pf-text-primary); margin-bottom: 4px;">Academic / Work Email</label>
                  <input id="auth-email" type="email" required placeholder="scholar@university.edu" class="pf-input" style="width: 100%; box-sizing: border-box; font-size: 13px; padding: 8px 12px; border-radius: 10px; border: 1px solid var(--pf-border-default); background: var(--pf-bg-surface);">
                </div>

                <div>
                  <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 4px;">
                    <label style="font-size: 11px; font-weight: 600; color: var(--pf-text-primary);">Password</label>
                    <button type="button" onclick="ProfFebAuth.sendMagicLink()" style="font-size: 11px; font-weight: 600; color: var(--pf-primary); background: none; border: none; cursor: pointer; text-decoration: underline;">
                      Email Magic Link
                    </button>
                  </div>
                  <div style="position: relative;">
                    <input id="auth-password" type="password" required placeholder="•••••••• (min 6 characters)" class="pf-input" style="width: 100%; box-sizing: border-box; font-size: 13px; padding: 8px 36px 8px 12px; border-radius: 10px; border: 1px solid var(--pf-border-default); background: var(--pf-bg-surface);">
                    <button type="button" onclick="ProfFebAuth.togglePasswordVisibility('auth-password', this)" tabindex="-1" style="position: absolute; right: 8px; top: 50%; transform: translateY(-50%); background: none; border: none; cursor: pointer; color: var(--pf-text-muted); padding: 4px;" title="Show/Hide Password">
                      <svg id="eye-icon-auth-password" style="width: 16px; height: 16px;" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"/><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z"/></svg>
                    </button>
                  </div>
                </div>

                <button id="btn-auth-submit" type="submit" class="pf-btn pf-btn-primary" style="width: 100%; margin-top: 6px; padding: 10px 16px; border-radius: 12px; font-size: 13px; font-weight: 700; display: flex; align-items: center; justify-content: center; gap: 8px;">
                  <span id="btn-auth-label">Sign In to ProfFeb</span>
                </button>
              </form>

              <!-- Footer terms -->
              <p style="margin: 1.25rem 0 0; text-align: center; font-size: 11px; color: var(--pf-text-muted);">
                By continuing, you agree to ProfFeb's Academic <a href="#" style="color: var(--pf-text-secondary); text-decoration: underline;">Terms</a> & <a href="#" style="color: var(--pf-text-secondary); text-decoration: underline;">Privacy Policy</a>.
              </p>
            </div>
          </div>
        </div>
      `;
      document.body.insertAdjacentHTML('beforeend', modalHtml);

      // Close modal on backdrop click
      const overlay = document.getElementById('proffeb-auth-modal-overlay');
      if (overlay) {
        overlay.addEventListener('click', (e) => {
          if (e.target === overlay) ProfFebAuth.closeModal();
        });
      }
    },

    openModal(mode = 'signin') {
      this.injectAuthModal();
      this.switchTab(mode);
      const overlay = document.getElementById('proffeb-auth-modal-overlay');
      if (overlay) overlay.classList.add('active');
    },

    closeModal() {
      const overlay = document.getElementById('proffeb-auth-modal-overlay');
      if (overlay) overlay.classList.remove('active');
      this.clearAlert();
    },

    switchTab(mode) {
      const tabIn = document.getElementById('tab-auth-signin');
      const tabUp = document.getElementById('tab-auth-signup');
      const nameField = document.getElementById('field-auth-fullname');
      const submitLabel = document.getElementById('btn-auth-label');

      if (!tabIn || !tabUp || !nameField || !submitLabel) return;

      if (mode === 'signup') {
        tabUp.style.background = 'var(--pf-bg-surface)';
        tabUp.style.color = 'var(--pf-primary)';
        tabUp.style.boxShadow = 'var(--pf-shadow-xs)';
        tabIn.style.background = 'transparent';
        tabIn.style.color = 'var(--pf-text-secondary)';
        tabIn.style.boxShadow = 'none';
        nameField.style.display = 'block';
        submitLabel.textContent = 'Create Free Scholar Account';
        this.currentMode = 'signup';
      } else {
        tabIn.style.background = 'var(--pf-bg-surface)';
        tabIn.style.color = 'var(--pf-primary)';
        tabIn.style.boxShadow = 'var(--pf-shadow-xs)';
        tabUp.style.background = 'transparent';
        tabUp.style.color = 'var(--pf-text-secondary)';
        tabUp.style.boxShadow = 'none';
        nameField.style.display = 'none';
        submitLabel.textContent = 'Sign In to ProfFeb';
        this.currentMode = 'signin';
      }
      this.clearAlert();
    },

    togglePasswordVisibility(inputId, btn) {
      const input = document.getElementById(inputId);
      if (!input) return;
      const isPassword = input.type === 'password';
      input.type = isPassword ? 'text' : 'password';

      const icon = btn.querySelector('svg');
      if (icon) {
        icon.innerHTML = isPassword
          ? '<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13.875 18.825A10.05 10.05 0 0112 19c-4.478 0-8.268-2.943-9.543-7a9.97 9.97 0 011.563-3.029m5.858.908a3 3 0 114.243 4.243M9.878 9.878l4.242 4.242M9.88 9.88l-3.29-3.29m7.532 7.532l3.29 3.29M3 3l18 18"/>'
          : '<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"/><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z"/>';
      }
    },

    showAlert(message, isError = true) {
      const box = document.getElementById('auth-alert-box');
      if (!box) return;
      box.textContent = message;
      box.style.display = 'block';
      if (isError) {
        box.style.background = 'rgba(239, 68, 68, 0.1)';
        box.style.color = 'var(--pf-danger)';
        box.style.border = '1px solid rgba(239, 68, 68, 0.25)';
      } else {
        box.style.background = 'rgba(16, 185, 129, 0.1)';
        box.style.color = 'var(--pf-success)';
        box.style.border = '1px solid rgba(16, 185, 129, 0.25)';
      }
    },

    clearAlert() {
      const box = document.getElementById('auth-alert-box');
      if (box) box.style.display = 'none';
    },

    async signInWithGoogle() {
      if (!this.supabase) {
        this.showAlert('Authentication service is initializing. Please try again.');
        return;
      }
      const btn = document.getElementById('btn-google-oauth');
      const label = document.getElementById('btn-google-label');
      if (btn && label) {
        btn.disabled = true;
        label.innerHTML = '<span class="pf-spinner" style="margin-right:6px;"></span> Connecting with Google...';
      }

      try {
        const redirectUrl = window.location.origin + window.location.pathname;
        const { error } = await this.supabase.auth.signInWithOAuth({
          provider: 'google',
          options: {
            redirectTo: redirectUrl
          }
        });
        if (error) throw error;
      } catch (err) {
        if (btn && label) {
          btn.disabled = false;
          label.textContent = 'Continue with Google';
        }
        this.showAlert(err.message || 'Google sign in could not be initiated.');
      }
    },

    async handleFormSubmit(e) {
      e.preventDefault();
      const email = document.getElementById('auth-email').value.trim();
      const password = document.getElementById('auth-password').value;
      const fullName = document.getElementById('auth-fullname')?.value.trim();
      const btn = document.getElementById('btn-auth-submit');
      const label = document.getElementById('btn-auth-label');

      if (!email || !password) {
        this.showAlert('Please fill in both email and password.');
        return;
      }

      if (password.length < 6) {
        this.showAlert('Password must be at least 6 characters.');
        return;
      }

      if (!this.supabase) {
        this.showAlert('Authentication service is not configured.');
        return;
      }

      btn.disabled = true;
      const originalText = label.textContent;
      label.innerHTML = `<span class="pf-spinner" style="margin-right:6px;"></span> ${this.currentMode === 'signup' ? 'Creating scholar workspace...' : 'Signing in...'}`;

      try {
        if (this.currentMode === 'signup') {
          const { data, error } = await this.supabase.auth.signUp({
            email,
            password,
            options: {
              data: {
                full_name: fullName || email.split('@')[0],
                tier: 'scholar',
                academic_title: 'PhD Scholar'
              }
            }
          });
          if (error) throw error;

          if (data.session) {
            this.currentUser = data.session.user;
            this.token = data.session.access_token;
            this.showAlert('Account created! Welcome to ProfFeb.', false);
            setTimeout(() => {
              this.closeModal();
              this.openProfileModal();
            }, 600);
          } else {
            this.showAlert('Verification link sent! Check your inbox to confirm.', false);
          }
        } else {
          const { data, error } = await this.supabase.auth.signInWithPassword({
            email,
            password
          });
          if (error) throw error;

          this.currentUser = data.session.user;
          this.token = data.session.access_token;
          this.showAlert('Signed in successfully!', false);
          setTimeout(() => this.closeModal(), 500);
        }
      } catch (err) {
        this.showAlert(err.message || 'Authentication failed. Please verify credentials.');
      } finally {
        btn.disabled = false;
        label.textContent = originalText;
      }
    },

    async sendMagicLink() {
      const email = document.getElementById('auth-email').value.trim();
      if (!email) {
        this.showAlert('Please enter your email above to receive a Magic Link.');
        return;
      }
      if (!this.supabase) {
        this.showAlert('Supabase is not configured.');
        return;
      }

      try {
        const { error } = await this.supabase.auth.signInWithOtp({
          email,
          options: {
            emailRedirectTo: window.location.origin + window.location.pathname
          }
        });
        if (error) throw error;
        this.showAlert('Magic Link sent! Check your inbox to sign in instantly.', false);
      } catch (err) {
        this.showAlert(err.message || 'Could not send magic link.');
      }
    },

    // -------------------------------------------------------------
    // PROFESSIONAL SCHOLAR PROFILE MODAL
    // -------------------------------------------------------------
    injectProfileModal() {
      if (document.getElementById('proffeb-profile-modal-overlay')) return;

      const modalHtml = `
        <div id="proffeb-profile-modal-overlay" class="pf-modal-overlay" style="z-index: 1000;">
          <div class="pf-modal" style="max-width: 620px; border-radius: 24px; box-shadow: var(--pf-shadow-2xl); background: var(--pf-bg-surface-elevated); max-height: 90vh; display: flex; flex-direction: column;">
            
            <!-- Modal Header Banner -->
            <div style="padding: 1.5rem 1.5rem 1.25rem; border-bottom: 1px solid var(--pf-border-subtle); background: linear-gradient(135deg, rgba(37,99,235,0.08) 0%, rgba(13,148,136,0.08) 50%, rgba(124,58,237,0.08) 100%); position: relative;">
              <button type="button" onclick="ProfFebAuth.closeProfileModal()" class="pf-btn pf-btn-ghost pf-btn-sm" style="position: absolute; right: 1rem; top: 1rem; border-radius: 50%; width: 28px; height: 28px; padding: 0; display: flex; align-items: center; justify-content: center; color: var(--pf-text-muted);" aria-label="Close">
                ✕
              </button>
              
              <div style="display: flex; align-items: center; gap: 1rem;">
                <div id="pf-profile-avatar-container" style="position: relative;">
                  <div id="pf-profile-avatar-preview" style="width: 60px; height: 60px; border-radius: 18px; background: linear-gradient(135deg, var(--pf-primary), var(--pf-accent-scout)); color: #fff; display: flex; align-items: center; justify-content: center; font-weight: 800; font-size: 22px; box-shadow: var(--pf-shadow-md); border: 2px solid var(--pf-bg-surface);">
                    P
                  </div>
                  <span style="position: absolute; bottom: -2px; right: -2px; width: 14px; height: 14px; background: var(--pf-success); border-radius: 50%; border: 2px solid var(--pf-bg-surface);"></span>
                </div>
                <div style="flex: 1; min-width: 0;">
                  <div style="display: flex; align-items: center; gap: 8px; flex-wrap: wrap;">
                    <h2 id="pf-profile-display-name" style="font-size: 18px; font-weight: 700; margin: 0; color: var(--pf-text-primary); line-height: 1.2;">Scholar Profile</h2>
                    <span id="pf-profile-tier-badge" style="font-size: 10px; font-weight: 700; font-family: var(--pf-font-mono); text-transform: uppercase; padding: 2px 8px; border-radius: 999px; background: var(--pf-accent-studio-subtle); color: var(--pf-primary); border: 1px solid rgba(37,99,235,0.2);">
                      Scholar Pass
                    </span>
                  </div>
                  <p id="pf-profile-display-email" style="font-size: 12px; margin: 3px 0 0; color: var(--pf-text-muted); font-family: var(--pf-font-mono); overflow: hidden; text-overflow: ellipsis;">
                    scholar@university.edu
                  </p>
                </div>
              </div>
            </div>

            <!-- Scrollable Body -->
            <div style="padding: 1.5rem; overflow-y: auto; flex: 1; display: flex; flex-direction: column; gap: 1.25rem;">
              
              <!-- Research Productivity HUD -->
              <div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; padding: 12px; border-radius: 16px; background: var(--pf-bg-surface-subtle); border: 1px solid var(--pf-border-subtle);">
                <div style="text-align: center;">
                  <div id="pf-profile-stat-papers" style="font-size: 18px; font-weight: 800; color: var(--pf-primary); line-height: 1.2;">0</div>
                  <div style="font-size: 10px; font-weight: 600; color: var(--pf-text-muted); text-transform: uppercase; margin-top: 2px;">Papers Synced</div>
                </div>
                <div style="text-align: center; border-left: 1px solid var(--pf-border-subtle); border-right: 1px solid var(--pf-border-subtle);">
                  <div id="pf-profile-stat-audio" style="font-size: 18px; font-weight: 800; color: var(--pf-accent-scout); line-height: 1.2;">0.0</div>
                  <div style="font-size: 10px; font-weight: 600; color: var(--pf-text-muted); text-transform: uppercase; margin-top: 2px;">Audio Mins</div>
                </div>
                <div style="text-align: center;">
                  <div id="pf-profile-stat-venues" style="font-size: 18px; font-weight: 800; color: var(--pf-accent-radar); line-height: 1.2;">1</div>
                  <div style="font-size: 10px; font-weight: 600; color: var(--pf-text-muted); text-transform: uppercase; margin-top: 2px;">Watchlist Items</div>
                </div>
              </div>

              <!-- Academic Credentials Form -->
              <div>
                <h4 style="font-size: 12px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.05em; color: var(--pf-text-secondary); margin: 0 0 10px;">
                  Academic Identity & Credentials
                </h4>
                
                <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 12px;">
                  <div>
                    <label style="display: block; font-size: 11px; font-weight: 600; color: var(--pf-text-primary); margin-bottom: 4px;">Full Name</label>
                    <input id="pf-input-fullname" type="text" placeholder="e.g. Dr. Jane Smith" class="pf-input" style="width: 100%; box-sizing: border-box; font-size: 13px; padding: 8px 12px; border-radius: 10px; border: 1px solid var(--pf-border-default); background: var(--pf-bg-surface);">
                  </div>

                  <div>
                    <label style="display: block; font-size: 11px; font-weight: 600; color: var(--pf-text-primary); margin-bottom: 4px;">Academic Role / Title</label>
                    <select id="pf-input-title" class="pf-input" style="width: 100%; box-sizing: border-box; font-size: 13px; padding: 8px 12px; border-radius: 10px; border: 1px solid var(--pf-border-default); background: var(--pf-bg-surface);">
                      <option value="PhD Candidate">PhD Candidate / Doctoral Researcher</option>
                      <option value="Postdoctoral Fellow">Postdoctoral Research Fellow</option>
                      <option value="Assistant Professor">Assistant Professor</option>
                      <option value="Associate Professor">Associate Professor</option>
                      <option value="Professor">Full Professor / Chair</option>
                      <option value="Principal Investigator">Principal Investigator (PI)</option>
                      <option value="Research Scientist">Industry / National Lab Scientist</option>
                      <option value="Independent Scholar">Independent Scholar & Author</option>
                      <option value="Graduate Student">Graduate / Masters Student</option>
                    </select>
                  </div>

                  <div>
                    <label style="display: block; font-size: 11px; font-weight: 600; color: var(--pf-text-primary); margin-bottom: 4px;">Primary Institution</label>
                    <input id="pf-input-institution" type="text" placeholder="e.g. Stanford University, MIT CSAIL, Oxford" class="pf-input" style="width: 100%; box-sizing: border-box; font-size: 13px; padding: 8px 12px; border-radius: 10px; border: 1px solid var(--pf-border-default); background: var(--pf-bg-surface);">
                  </div>

                  <div>
                    <label style="display: block; font-size: 11px; font-weight: 600; color: var(--pf-text-primary); margin-bottom: 4px;">Primary Research Field</label>
                    <input id="pf-input-field" type="text" placeholder="e.g. Deep Learning, Computational Biology" class="pf-input" style="width: 100%; box-sizing: border-box; font-size: 13px; padding: 8px 12px; border-radius: 10px; border: 1px solid var(--pf-border-default); background: var(--pf-bg-surface);">
                  </div>
                </div>
              </div>

              <!-- Spoken Neural Audio Voice Preferences -->
              <div>
                <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 6px;">
                  <h4 style="font-size: 12px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.05em; color: var(--pf-text-secondary); margin: 0;">
                    Preferred Spoken Audio Briefing Voice
                  </h4>
                  <button type="button" onclick="ProfFebAuth.testVoiceSample()" class="pf-btn pf-btn-ghost pf-btn-sm" style="font-size: 11px; padding: 3px 8px; color: var(--pf-primary); display: flex; align-items: center; gap: 4px;">
                    <i data-lucide="volume-2" style="width: 13px; height: 13px;"></i>
                    <span>Preview Voice</span>
                  </button>
                </div>
                
                <select id="pf-input-voice" class="pf-input" style="width: 100%; box-sizing: border-box; font-size: 13px; padding: 8px 12px; border-radius: 10px; border: 1px solid var(--pf-border-default); background: var(--pf-bg-surface);">
                  <option value="en-NG-AbeoNeural">🇬🇭 Abeo (West Africa / Ghana - Male, Expressive & Natural) [Default]</option>
                  <option value="en-NG-EzinneNeural">🇬🇭 Ezinne (West Africa / Ghana - Female, Melodic & Clear)</option>
                  <option value="en-KE-ChilembaNeural">🇰🇪 Chilemba (East Africa / Kenya - Male, Scholarly)</option>
                  <option value="en-KE-AsiliaNeural">🇰🇪 Asilia (East Africa / Kenya - Female, Articulate)</option>
                  <option value="en-ZA-LukeNeural">🇿🇦 Luke (South Africa - Male, Crisp & Modern)</option>
                  <option value="en-ZA-LeahNeural">🇿🇦 Leah (South Africa - Female, Warm)</option>
                  <option value="en-US-ChristopherNeural">🇺🇸 Christopher (US - Authoritative, Mentor)</option>
                  <option value="en-US-JennyNeural">🇺🇸 Jenny (US - Warm, Engaging)</option>
                  <option value="en-US-GuyNeural">🇺🇸 Guy (US - Natural, Conversational)</option>
                  <option value="en-US-AriaNeural">🇺🇸 Aria (US - Professional, Clear)</option>
                  <option value="en-GB-RyanNeural">🇬🇧 Ryan (UK - Academic, Articulate)</option>
                  <option value="en-GB-SoniaNeural">🇬🇧 Sonia (UK - Formal, Scholarly)</option>
                  <option value="en-AU-WilliamNeural">🇦🇺 William (Australia - Relaxed, Direct)</option>
                  <option value="en-IN-PrabhatNeural">🇮🇳 Prabhat (India - Professional, Articulate)</option>
                  <option value="en-IN-NeerjaNeural">🇮🇳 Neerja (India - Melodic, Clear)</option>
                  <option value="en-CA-LiamNeural">🇨🇦 Liam (Canada - Calm & Modern)</option>
                  <option value="en-IE-ConnorNeural">🇮🇪 Connor (Ireland - Scholarly & Warm)</option>
                </select>
                <p style="font-size: 11px; color: var(--pf-text-muted); margin: 4px 0 0;">
                  This neural voice will narrate your academic papers, executive summaries, and mathematical theorem explanations.
                </p>
              </div>

              <!-- Connected Workstation Tools -->
              <div style="padding: 12px 14px; border-radius: 14px; background: var(--pf-bg-surface-subtle); border: 1px solid var(--pf-border-subtle); display: flex; align-items: center; justify-content: space-between;">
                <div style="display: flex; align-items: center; gap: 10px;">
                  <div style="width: 32px; height: 32px; border-radius: 10px; background: var(--pf-accent-studio-subtle); color: var(--pf-engine-studio); display: flex; align-items: center; justify-content: center;">
                    <i data-lucide="library" style="width: 16px; height: 16px;"></i>
                  </div>
                  <div>
                    <div style="font-size: 12px; font-weight: 700; color: var(--pf-text-primary);">Zotero Library Integration</div>
                    <div id="pf-profile-zotero-status" style="font-size: 11px; color: var(--pf-text-muted);">Syncing from personal or lab library</div>
                  </div>
                </div>
                <button type="button" onclick="ProfFebAuth.closeProfileModal(); if(window.ProfFebUI&&ProfFebUI.zotero) ProfFebUI.zotero.open();" class="pf-btn pf-btn-secondary pf-btn-sm" style="font-size: 11px;">
                  Configure API Key
                </button>
              </div>

            </div>

            <!-- Modal Footer Actions -->
            <div style="padding: 1rem 1.5rem; border-top: 1px solid var(--pf-border-subtle); display: flex; align-items: center; justify-content: flex-end; gap: 10px; background: var(--pf-bg-surface-subtle); border-bottom-left-radius: 24px; border-bottom-right-radius: 24px;">
              <button type="button" onclick="ProfFebAuth.closeProfileModal()" class="pf-btn pf-btn-ghost pf-btn-sm">
                Cancel
              </button>
              <button id="pf-profile-save-btn" type="button" onclick="ProfFebAuth.saveProfile()" class="pf-btn pf-btn-primary pf-btn-sm" style="font-weight: 700; display: flex; align-items: center; gap: 6px;">
                <i data-lucide="check" style="width: 14px; height: 14px;"></i>
                <span>Save Academic Profile</span>
              </button>
            </div>

          </div>
        </div>
      `;
      document.body.insertAdjacentHTML('beforeend', modalHtml);

      // Close modal on backdrop click
      const overlay = document.getElementById('proffeb-profile-modal-overlay');
      if (overlay) {
        overlay.addEventListener('click', (e) => {
          if (e.target === overlay) ProfFebAuth.closeProfileModal();
        });
      }
    },

    async openProfileModal() {
      if (!this.currentUser) {
        this.openModal('signin');
        return;
      }
      this.injectProfileModal();
      await this.loadUserProfile();
      this.populateProfileModal();
      const overlay = document.getElementById('proffeb-profile-modal-overlay');
      if (overlay) overlay.classList.add('active');
      if (window.lucide && typeof window.lucide.createIcons === 'function') {
        window.lucide.createIcons();
      }
    },

    closeProfileModal() {
      const overlay = document.getElementById('proffeb-profile-modal-overlay');
      if (overlay) overlay.classList.remove('active');
    },

    populateProfileModal() {
      if (!this.currentUser) return;
      const meta = this.currentUser.user_metadata || {};
      const name = this.profile?.full_name || meta.full_name || meta.name || this.currentUser.email.split('@')[0];
      const initials = (name || 'U').slice(0, 2).toUpperCase();
      const avatarUrl = this.profile?.avatar_url || meta.avatar_url || meta.picture || '';
      const email = this.currentUser.email || '';
      const title = this.profile?.academic_title || meta.academic_title || 'PhD Candidate';
      const institution = this.profile?.institution || meta.institution || '';
      const field = this.profile?.research_field || meta.research_field || '';
      const voice = this.profile?.preferred_voice || meta.preferred_voice || 'en-NG-AbeoNeural';
      const tier = (this.profile?.tier || meta.tier || 'Scholar').toUpperCase();

      const nameEl = document.getElementById('pf-profile-display-name');
      const emailEl = document.getElementById('pf-profile-display-email');
      const tierBadge = document.getElementById('pf-profile-tier-badge');
      const avatarContainer = document.getElementById('pf-profile-avatar-preview');

      if (nameEl) nameEl.textContent = name;
      if (emailEl) emailEl.textContent = email;
      if (tierBadge) tierBadge.textContent = `${tier} PASS`;

      if (avatarContainer) {
        if (avatarUrl) {
          avatarContainer.innerHTML = `<img src="${avatarUrl}" alt="${name}" style="width:100%;height:100%;border-radius:16px;object-fit:cover;" onerror="this.outerHTML='${initials}'">`;
        } else {
          avatarContainer.textContent = initials;
        }
      }

      // Populate form fields
      const inputName = document.getElementById('pf-input-fullname');
      const inputTitle = document.getElementById('pf-input-title');
      const inputInstitution = document.getElementById('pf-input-institution');
      const inputField = document.getElementById('pf-input-field');
      const inputVoice = document.getElementById('pf-input-voice');

      if (inputName) inputName.value = name;
      if (inputTitle) inputTitle.value = title;
      if (inputInstitution) inputInstitution.value = institution;
      if (inputField) inputField.value = field;
      if (inputVoice) inputVoice.value = voice;

      // Stats
      const statPapers = document.getElementById('pf-profile-stat-papers');
      const statAudio = document.getElementById('pf-profile-stat-audio');
      const statVenues = document.getElementById('pf-profile-stat-venues');

      if (statPapers) statPapers.textContent = this.stats.papers_synced || 0;
      if (statAudio) statAudio.textContent = this.stats.audio_minutes || 0.0;
      if (statVenues) statVenues.textContent = this.stats.watchlist_count || 1;

      // Zotero status
      const zoteroStatus = document.getElementById('pf-profile-zotero-status');
      if (zoteroStatus) {
        const hasZotero = Boolean(this.profile?.zotero_user_id || this.profile?.has_zotero_key);
        zoteroStatus.textContent = hasZotero
          ? `Connected to Library (${this.profile.zotero_user_id || 'Active'})`
          : 'Not connected — configure API key to sync papers';
        zoteroStatus.style.color = hasZotero ? 'var(--pf-success)' : 'var(--pf-text-muted)';
      }
    },

    async saveProfile() {
      const btn = document.getElementById('pf-profile-save-btn');
      const fullName = document.getElementById('pf-input-fullname')?.value.trim() || '';
      const academicTitle = document.getElementById('pf-input-title')?.value || 'PhD Scholar';
      const institution = document.getElementById('pf-input-institution')?.value.trim() || '';
      const researchField = document.getElementById('pf-input-field')?.value.trim() || '';
      const preferredVoice = document.getElementById('pf-input-voice')?.value || 'en-NG-AbeoNeural';

      if (btn) {
        btn.disabled = true;
        btn.innerHTML = '<span class="pf-spinner" style="margin-right:6px;"></span> Saving Changes...';
      }

      try {
        const res = await this.fetchWithAuth('/api/user/profile', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            full_name: fullName,
            academic_title: academicTitle,
            institution: institution,
            research_field: researchField,
            preferred_voice: preferredVoice
          })
        });

        if (!res.ok) throw new Error('Could not update profile');

        // Update local state
        if (!this.profile) this.profile = {};
        this.profile.full_name = fullName;
        this.profile.academic_title = academicTitle;
        this.profile.institution = institution;
        this.profile.research_field = researchField;
        this.profile.preferred_voice = preferredVoice;

        if (this.currentUser && this.currentUser.user_metadata) {
          Object.assign(this.currentUser.user_metadata, {
            full_name: fullName,
            academic_title: academicTitle,
            institution: institution,
            research_field: researchField,
            preferred_voice: preferredVoice
          });
        }

        this.renderNavbarUI();
        this.closeProfileModal();

        if (window.ProfFebUI && ProfFebUI.toast) {
          ProfFebUI.toast({
            title: 'Profile Updated',
            message: 'Your academic credentials and neural voice settings have been saved.',
            type: 'success'
          });
        }
      } catch (err) {
        alert(err.message || 'Failed to update academic profile.');
      } finally {
        if (btn) {
          btn.disabled = false;
          btn.innerHTML = '<i data-lucide="check" style="width: 14px; height: 14px;"></i><span>Save Academic Profile</span>';
          if (window.lucide && typeof window.lucide.createIcons === 'function') window.lucide.createIcons();
        }
      }
    },

    testVoiceSample() {
      const voiceSelect = document.getElementById('pf-input-voice');
      const voiceId = voiceSelect ? voiceSelect.value : 'en-NG-AbeoNeural';
      const sampleText = 'Welcome to ProfFeb. I will be your academic mentor, breaking down complex mathematical proofs and research manuscripts.';

      // Try synthesized preview via Web Speech API or friendly audible feedback
      try {
        if ('speechSynthesis' in window) {
          window.speechSynthesis.cancel();
          const utterance = new SpeechSynthesisUtterance(sampleText);
          utterance.rate = 1.0;
          utterance.pitch = 1.0;

          // Attempt to match lang
          const langMatch = voiceId.slice(0, 5); // e.g. en-US, en-GB, en-NG
          utterance.lang = langMatch;

          const voices = window.speechSynthesis.getVoices();
          const matchingVoice = voices.find(v => v.lang.startsWith(langMatch) || v.name.includes(voiceId.split('-')[2] || ''));
          if (matchingVoice) utterance.voice = matchingVoice;

          window.speechSynthesis.speak(utterance);
        }
      } catch (e) {}

      if (window.ProfFebUI && ProfFebUI.toast) {
        ProfFebUI.toast({
          title: 'Voice Selected',
          message: `Previewing ${voiceId.split('-')[2] || voiceId}... Spoken briefings will use this neural model.`,
          type: 'info',
          duration: 3000
        });
      }
    },

    async signOut() {
      if (this.supabase) {
        await this.supabase.auth.signOut();
      }
      this.currentUser = null;
      this.token = null;
      this.profile = null;
      this.renderNavbarUI();
      if (window.ProfFebUI && ProfFebUI.toast) {
        ProfFebUI.toast({
          title: 'Signed Out',
          message: 'You have been signed out of ProfFeb.',
          type: 'info'
        });
      }
      setTimeout(() => window.location.reload(), 500);
    }
  };

  window.clearProfFebCache = () => window.ProfFebAuth && window.ProfFebAuth.clearCache();

  // Auto-init on page load
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => ProfFebAuth.init());
  } else {
    ProfFebAuth.init();
  }
})();
