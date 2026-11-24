/**
 * ProfFeb — Global SaaS Authentication & Session Manager
 * Powered by Supabase Auth with Google OAuth & Email/Password
 */

(function () {
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
    config: null,
    token: null,

    async init() {
      try {
        // 1. Fetch public config from backend
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
          }

          // Listen for reactive auth changes (Sign In, Sign Out, Token Refresh)
          this.supabase.auth.onAuthStateChange((event, session) => {
            if (session) {
              this.currentUser = session.user;
              this.token = session.access_token;
            } else {
              this.currentUser = null;
              this.token = null;
            }
            this.renderNavbarUI();
            window.dispatchEvent(new CustomEvent('proffeb-auth-changed', { detail: { user: this.currentUser, token: this.token } }));
          });
        }
      } catch (err) {
        console.warn('ProfFeb Auth initialization note:', err);
      }

      this.injectAuthModal();
      this.renderNavbarUI();
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
      alert('ProfFeb cache cleared successfully! Reloading...');
      window.location.reload();
    },

    renderNavbarUI() {
      const container = document.getElementById('user-nav-container');
      if (!container) return;

      if (this.currentUser) {
        const name = this.currentUser.user_metadata?.full_name || this.currentUser.email.split('@')[0];
        const initials = (name || 'U').slice(0, 2).toUpperCase();
        const tier = (this.currentUser.user_metadata?.tier || 'Scholar').toUpperCase();

        container.innerHTML = `
          <div class="relative inline-block text-left" id="user-menu-root">
            <button id="user-menu-btn" type="button" class="pf-btn pf-btn-secondary pf-btn-sm" style="display:flex;align-items:center;gap:8px;padding:4px 10px;border-radius:12px;">
              <div style="width:24px;height:24px;border-radius:8px;background:linear-gradient(135deg,var(--pf-primary),var(--pf-accent-scout));color:#fff;display:flex;align-items:center;justify-content:center;font-weight:700;font-size:11px;">
                ${initials}
              </div>
              <div class="text-left hidden sm:block" style="text-align:left;">
                <div style="font-size:12px;font-weight:600;color:var(--pf-text-primary);line-height:1.2;max-width:110px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${name}</div>
                <span style="font-size:9px;font-family:var(--pf-font-mono);font-weight:700;color:var(--pf-primary);text-transform:uppercase;">${tier}</span>
              </div>
              <i data-lucide="chevron-down" style="width:14px;height:14px;color:var(--pf-text-muted);"></i>
            </button>

            <!-- Dropdown Menu -->
            <div id="user-menu-dropdown" class="hidden absolute right-0 mt-2 w-64 rounded-2xl py-2 z-50 animate-in fade-in zoom-in-95 duration-100" style="background:var(--pf-bg-surface-elevated);border:1px solid var(--pf-border-subtle);color:var(--pf-text-primary);box-shadow:var(--pf-shadow-lg);">
              <div class="px-4 py-2 border-b" style="border-color:var(--pf-border-subtle);">
                <p style="font-size:10px;color:var(--pf-text-muted);font-weight:500;margin:0;">Signed in as</p>
                <p style="font-size:12px;font-weight:700;color:var(--pf-text-primary);margin:2px 0 0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${this.currentUser.email}</p>
              </div>
              <a href="/app" class="flex items-center gap-2.5 px-4 py-2 text-xs font-medium transition" style="color:var(--pf-text-secondary);text-decoration:none;">
                <i data-lucide="headphones" style="width:14px;height:14px;color:var(--pf-engine-studio);"></i> Research Studio
              </a>
              <a href="/conferences" class="flex items-center gap-2.5 px-4 py-2 text-xs font-medium transition" style="color:var(--pf-text-secondary);text-decoration:none;">
                <i data-lucide="calendar" style="width:14px;height:14px;color:var(--pf-engine-scout);"></i> Conference Scout
              </a>
              <a href="/agent" class="flex items-center gap-2.5 px-4 py-2 text-xs font-medium transition" style="color:var(--pf-text-secondary);text-decoration:none;">
                <i data-lucide="bot" style="width:14px;height:14px;color:var(--pf-engine-copilot);"></i> Academic Co-Pilot
              </a>
              <div class="border-t my-1" style="border-color:var(--pf-border-subtle);"></div>
              <button type="button" onclick="if(window.ProfFebUI&&ProfFebUI.zotero)ProfFebUI.zotero.open()" class="w-full text-left flex items-center gap-2.5 px-4 py-2 text-xs font-medium transition" style="color:var(--pf-text-secondary);background:transparent;border:none;cursor:pointer;">
                <i data-lucide="library" style="width:14px;height:14px;color:var(--pf-primary);"></i> Zotero Account Setup
              </button>
              <button type="button" onclick="if(window.ProfFebUI&&ProfFebUI.settings)ProfFebUI.settings.open()" class="w-full text-left flex items-center gap-2.5 px-4 py-2 text-xs font-medium transition" style="color:var(--pf-text-secondary);background:transparent;border:none;cursor:pointer;">
                <i data-lucide="settings" style="width:14px;height:14px;color:var(--pf-text-muted);"></i> Workstation Settings
              </button>
              <button type="button" onclick="ProfFebAuth.clearCache()" class="w-full text-left flex items-center gap-2.5 px-4 py-2 text-xs font-medium transition" style="color:var(--pf-text-muted);background:transparent;border:none;cursor:pointer;">
                <i data-lucide="refresh-cw" style="width:14px;height:14px;color:var(--pf-text-muted);"></i> Clear Cache & Reload
              </button>
              <div class="border-t my-1" style="border-color:var(--pf-border-subtle);"></div>
              <button type="button" onclick="ProfFebAuth.signOut()" class="w-full text-left flex items-center gap-2.5 px-4 py-2 text-xs font-semibold transition" style="color:var(--pf-danger);background:transparent;border:none;cursor:pointer;">
                <i data-lucide="log-out" style="width:14px;height:14px;color:var(--pf-danger);"></i> Sign Out
              </button>
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

    injectAuthModal() {
      if (document.getElementById('proffeb-auth-modal')) return;

      const modalHtml = `
        <div id="proffeb-auth-modal" class="fixed inset-0 z-50 hidden bg-slate-900/60 backdrop-blur-sm flex items-center justify-center p-4">
          <div class="relative w-full max-w-md bg-white rounded-3xl shadow-2xl border border-slate-100 overflow-hidden transform transition-all animate-in fade-in zoom-in-95 duration-150">
            <!-- Header bar with logo -->
            <div class="px-6 pt-6 pb-4 flex items-center justify-between border-b border-slate-100">
              <div class="flex items-center gap-2.5">
                <div class="w-8 h-8 rounded-xl bg-gradient-to-tr from-brand-600 to-scholar-600 flex items-center justify-center text-white font-bold text-sm shadow-sm">
                  P
                </div>
                <div>
                  <h3 class="text-sm font-bold text-slate-900 leading-tight">ProfFeb</h3>
                  <p class="text-[10px] text-slate-400 font-medium">Neural Research Workstation</p>
                </div>
              </div>
              <button onclick="ProfFebAuth.closeModal()" class="text-slate-400 hover:text-slate-600 p-1.5 rounded-full hover:bg-slate-100 transition">
                <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/></svg>
              </button>
            </div>

            <!-- Tab switcher -->
            <div class="flex border-b border-slate-100 bg-slate-50/60 p-1">
              <button id="tab-auth-signin" onclick="ProfFebAuth.switchTab('signin')" class="flex-1 py-2 text-xs font-bold rounded-xl transition text-brand-600 bg-white shadow-xs">
                Sign In
              </button>
              <button id="tab-auth-signup" onclick="ProfFebAuth.switchTab('signup')" class="flex-1 py-2 text-xs font-bold rounded-xl transition text-slate-500 hover:text-slate-800">
                Create Account
              </button>
            </div>

            <div class="p-6">
              <!-- One-Click Google OAuth -->
              <button id="btn-google-oauth" onclick="ProfFebAuth.signInWithGoogle()" type="button" class="w-full flex items-center justify-center gap-3 py-2.5 px-4 rounded-xl border border-slate-200 hover:bg-slate-50 text-slate-700 text-xs font-semibold shadow-xs transition">
                <svg class="w-4 h-4" viewBox="0 0 24 24">
                  <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"/>
                  <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/>
                  <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.06H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.94l2.85-2.22.81-.63z"/>
                  <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.06l3.66 2.84c.87-2.6 3.3-4.52 6.16-4.52z"/>
                </svg>
                Continue with Google
              </button>

              <div class="relative my-4">
                <div class="absolute inset-0 flex items-center"><div class="w-full border-t border-slate-100"></div></div>
                <div class="relative flex justify-center text-[10px] uppercase font-mono tracking-wider text-slate-400 bg-white px-2">
                  or with academic email
                </div>
              </div>

              <!-- Alerts -->
              <div id="auth-alert-box" class="hidden mb-3 p-3 rounded-xl text-xs font-medium"></div>

              <!-- Main Form -->
              <form id="proffeb-auth-form" onsubmit="ProfFebAuth.handleFormSubmit(event)" class="space-y-3">
                <div id="field-auth-fullname" class="hidden">
                  <label class="block text-[11px] font-semibold text-slate-700 mb-1">Full Name</label>
                  <input id="auth-fullname" type="text" placeholder="e.g. Dr. Jane Smith" class="w-full text-xs px-3.5 py-2.5 rounded-xl border border-slate-200 focus:outline-none focus:border-brand-500 focus:ring-1 focus:ring-brand-500 transition">
                </div>

                <div>
                  <label class="block text-[11px] font-semibold text-slate-700 mb-1">Academic / Work Email</label>
                  <input id="auth-email" type="email" required placeholder="scholar@university.edu" class="w-full text-xs px-3.5 py-2.5 rounded-xl border border-slate-200 focus:outline-none focus:border-brand-500 focus:ring-1 focus:ring-brand-500 transition">
                </div>

                <div>
                  <div class="flex items-center justify-between mb-1">
                    <label class="block text-[11px] font-semibold text-slate-700">Password</label>
                    <button type="button" onclick="ProfFebAuth.sendMagicLink()" class="text-[10px] font-semibold text-brand-600 hover:underline">
                      Email Magic Link instead
                    </button>
                  </div>
                  <input id="auth-password" type="password" required placeholder="••••••••" class="w-full text-xs px-3.5 py-2.5 rounded-xl border border-slate-200 focus:outline-none focus:border-brand-500 focus:ring-1 focus:ring-brand-500 transition">
                </div>

                <button id="btn-auth-submit" type="submit" class="w-full mt-2 py-2.5 px-4 rounded-xl bg-slate-900 hover:bg-brand-600 text-white font-bold text-xs shadow-sm hover:shadow transition flex items-center justify-center gap-2">
                  <span id="btn-auth-label">Sign In to ProfFeb</span>
                </button>
              </form>

              <!-- Footer terms -->
              <p class="mt-4 text-center text-[10px] text-slate-400">
                By continuing, you agree to ProfFeb's <a href="#" class="underline hover:text-slate-600">Terms of Service</a> & <a href="#" class="underline hover:text-slate-600">Privacy Policy</a>.
              </p>
            </div>
          </div>
        </div>
      `;
      document.body.insertAdjacentHTML('beforeend', modalHtml);
    },

    openModal(mode = 'signin') {
      this.injectAuthModal();
      this.switchTab(mode);
      const modal = document.getElementById('proffeb-auth-modal');
      if (modal) modal.classList.remove('hidden');
    },

    closeModal() {
      const modal = document.getElementById('proffeb-auth-modal');
      if (modal) modal.classList.add('hidden');
      this.clearAlert();
    },

    switchTab(mode) {
      const tabIn = document.getElementById('tab-auth-signin');
      const tabUp = document.getElementById('tab-auth-signup');
      const nameField = document.getElementById('field-auth-fullname');
      const submitLabel = document.getElementById('btn-auth-label');

      if (mode === 'signup') {
        tabUp.className = 'flex-1 py-2 text-xs font-bold rounded-xl transition text-brand-600 bg-white shadow-xs';
        tabIn.className = 'flex-1 py-2 text-xs font-bold rounded-xl transition text-slate-500 hover:text-slate-800';
        nameField.classList.remove('hidden');
        submitLabel.textContent = 'Create Free Scholar Account';
        this.currentMode = 'signup';
      } else {
        tabIn.className = 'flex-1 py-2 text-xs font-bold rounded-xl transition text-brand-600 bg-white shadow-xs';
        tabUp.className = 'flex-1 py-2 text-xs font-bold rounded-xl transition text-slate-500 hover:text-slate-800';
        nameField.classList.add('hidden');
        submitLabel.textContent = 'Sign In to ProfFeb';
        this.currentMode = 'signin';
      }
      this.clearAlert();
    },

    showAlert(message, isError = true) {
      const box = document.getElementById('auth-alert-box');
      if (!box) return;
      box.textContent = message;
      box.className = isError
        ? 'mb-3 p-3 rounded-xl text-xs font-medium bg-red-50 text-red-700 border border-red-200'
        : 'mb-3 p-3 rounded-xl text-xs font-medium bg-emerald-50 text-emerald-700 border border-emerald-200';
      box.classList.remove('hidden');
    },

    clearAlert() {
      const box = document.getElementById('auth-alert-box');
      if (box) box.classList.add('hidden');
    },

    async signInWithGoogle() {
      if (!this.supabase) {
        this.showAlert('Authentication service is currently unavailable. Please check backend config.');
        return;
      }
      try {
        const { error } = await this.supabase.auth.signInWithOAuth({
          provider: 'google',
          options: {
            redirectTo: window.location.href
          }
        });
        if (error) throw error;
      } catch (err) {
        this.showAlert(err.message || 'Google sign in failed');
      }
    },

    async handleFormSubmit(e) {
      e.preventDefault();
      const email = document.getElementById('auth-email').value.trim();
      const password = document.getElementById('auth-password').value;
      const fullName = document.getElementById('auth-fullname')?.value.trim();
      const btn = document.getElementById('btn-auth-submit');

      if (!email || !password) {
        this.showAlert('Please fill in both email and password.');
        return;
      }

      if (!this.supabase) {
        this.showAlert('Supabase credentials not configured in backend.');
        return;
      }

      btn.disabled = true;
      btn.classList.add('opacity-70');

      try {
        if (this.currentMode === 'signup') {
          const { data, error } = await this.supabase.auth.signUp({
            email,
            password,
            options: {
              data: {
                full_name: fullName || email.split('@')[0],
                tier: 'scholar'
              }
            }
          });
          if (error) throw error;

          if (data.session) {
            this.currentUser = data.session.user;
            this.token = data.session.access_token;
            this.showAlert('Account created! Welcome to ProfFeb.', false);
            setTimeout(() => this.closeModal(), 1000);
          } else {
            this.showAlert('Verification email sent! Check your inbox to confirm.', false);
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
          setTimeout(() => this.closeModal(), 800);
        }
      } catch (err) {
        this.showAlert(err.message || 'Authentication failed. Please verify credentials.');
      } finally {
        btn.disabled = false;
        btn.classList.remove('opacity-70');
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
            emailRedirectTo: window.location.href
          }
        });
        if (error) throw error;
        this.showAlert('Magic Link sent! Check your inbox to sign in instantly.', false);
      } catch (err) {
        this.showAlert(err.message || 'Could not send magic link.');
      }
    },

    async signOut() {
      if (this.supabase) {
        await this.supabase.auth.signOut();
      }
      this.currentUser = null;
      this.token = null;
      this.renderNavbarUI();
      window.location.reload();
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
