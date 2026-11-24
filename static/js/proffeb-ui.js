/**
 * ProfFeb UI Controller & Component Library
 * Default Light Mode, Lucide Icon Rendering, Command Palette,
 * Unified Toast System, and Settings Modal with Audio Cache Cleaner.
 */

(function () {
  'use strict';

  const ProfFebUI = {
    // 1. Theme Controller (LIGHT by default)
    theme: {
      get: function () {
        const stored = localStorage.getItem('proffeb_theme');
        if (stored) return stored;
        // Default to light theme per product design spec
        return 'light';
      },
      set: function (theme) {
        localStorage.setItem('proffeb_theme', theme);
        const root = document.documentElement;
        if (theme === 'dark') {
          root.classList.add('dark');
          root.setAttribute('data-theme', 'dark');
        } else {
          root.classList.remove('dark');
          root.setAttribute('data-theme', 'light');
        }
        
        // Update toggle buttons
        document.querySelectorAll('.pf-theme-toggle-label').forEach(el => {
          el.textContent = theme === 'dark' ? 'Light Mode' : 'Dark Mode';
        });

        // Re-render Lucide icons if available
        if (window.lucide && typeof window.lucide.createIcons === 'function') {
          setTimeout(() => window.lucide.createIcons(), 10);
        }

        window.dispatchEvent(new CustomEvent('proffeb-theme-changed', { detail: { theme } }));
      },
      toggle: function () {
        const current = this.get();
        const next = current === 'dark' ? 'light' : 'dark';
        this.set(next);
        ProfFebUI.toast({
          title: 'Theme Updated',
          message: `Switched to ${next === 'dark' ? 'Dark' : 'Light (Warm Editorial)'} mode.`,
          type: 'info',
          duration: 2500
        });
      },
      init: function () {
        this.set(this.get());
      }
    },

    // 2. Toast Notification Hub
    toast: function ({ title = '', message = '', type = 'info', duration = 3500 } = {}) {
      let container = document.getElementById('pf-toast-container');
      if (!container) {
        container = document.createElement('div');
        container.id = 'pf-toast-container';
        document.body.appendChild(container);
      }

      const colors = {
        success: 'var(--pf-success)',
        error: 'var(--pf-danger)',
        warning: 'var(--pf-warning)',
        info: 'var(--pf-primary)'
      };

      const toastEl = document.createElement('div');
      toastEl.className = 'pf-toast';
      toastEl.setAttribute('role', 'status');
      toastEl.innerHTML = `
        <div style="color: ${colors[type] || colors.info}; font-size: 16px; margin-top: 1px;">
          ${type === 'success' ? '✓' : type === 'error' ? '✕' : type === 'warning' ? '⚠' : 'ℹ'}
        </div>
        <div style="flex: 1; min-width: 0;">
          ${title ? `<div style="font-weight: 700; font-size: 13px; color: var(--pf-text-primary); margin-bottom: 2px;">${title}</div>` : ''}
          <div style="font-size: 13px; color: var(--pf-text-secondary); line-height: 1.4;">${message}</div>
        </div>
        <button type="button" style="background: transparent; border: none; font-size: 14px; cursor: pointer; color: var(--pf-text-muted); padding: 0 4px;" onclick="this.parentElement.remove()">✕</button>
      `;

      container.appendChild(toastEl);
      requestAnimationFrame(() => toastEl.classList.add('pf-toast-visible'));

      if (duration > 0) {
        setTimeout(() => {
          toastEl.classList.remove('pf-toast-visible');
          setTimeout(() => toastEl.remove(), 250);
        }, duration);
      }
    },

    // 3. Settings & Cache Clear Modal
    settings: {
      open: function () {
        let modal = document.getElementById('pf-settings-modal');
        if (!modal) {
          modal = document.createElement('div');
          modal.id = 'pf-settings-modal';
          modal.className = 'pf-modal-overlay';
          modal.innerHTML = `
            <div class="pf-modal">
              <div style="padding: 1.25rem 1.5rem; border-bottom: 1px solid var(--pf-border-subtle); display: flex; align-items: center; justify-content: space-between;">
                <div style="display: flex; align-items: center; gap: 0.625rem;">
                  <div style="width: 32px; height: 32px; border-radius: var(--pf-radius-sm); background: var(--pf-bg-surface-elevated); display: flex; align-items: center; justify-content: center; color: var(--pf-primary);">
                    <i data-lucide="settings" style="width: 18px; height: 18px;"></i>
                  </div>
                  <div>
                    <h3 style="font-size: 16px; font-weight: 700; margin: 0; color: var(--pf-text-primary);">Workstation Settings</h3>
                    <p style="font-size: 12px; margin: 0; color: var(--pf-text-muted);">Cache controls, neural voice preferences & storage</p>
                  </div>
                </div>
                <button type="button" class="pf-btn pf-btn-ghost pf-btn-sm" onclick="ProfFebUI.settings.close()">✕</button>
              </div>

              <div style="padding: 1.5rem; display: flex; flex-direction: column; gap: 1.25rem;">
                <!-- Zotero Reference Library Account Integration -->
                <div class="p-3.5 rounded-xl border" style="background: var(--pf-bg-surface-elevated); border-color: var(--pf-border-subtle);">
                  <div style="display: flex; justify-content: space-between; align-items: flex-start; gap: 1rem;">
                    <div>
                      <div style="display: flex; align-items: center; gap: 8px;">
                        <span style="font-size: 14px; font-weight: 700; color: var(--pf-text-primary);">Zotero Library Integration</span>
                        <span id="pf-zotero-status-indicator"></span>
                      </div>
                      <div style="font-size: 12px; color: var(--pf-text-muted); margin-top: 2px;">
                        Connect your personal Zotero User ID and API Key to import papers and PDFs.
                      </div>
                    </div>
                    <button type="button" class="pf-btn pf-btn-secondary pf-btn-sm" onclick="ProfFebUI.settings.close(); ProfFebUI.zotero.open();">
                      Configure
                    </button>
                  </div>
                </div>

                <!-- Audio Cache Controls -->
                <div class="p-3.5 rounded-xl border" style="background: var(--pf-bg-surface-elevated); border-color: var(--pf-border-subtle);">
                  <div style="display: flex; justify-content: space-between; align-items: flex-start; gap: 1rem;">
                    <div>
                      <div style="font-size: 14px; font-weight: 700; color: var(--pf-text-primary);">Audio & Manuscript Cache</div>
                      <div style="font-size: 12px; color: var(--pf-text-muted); margin-top: 2px;">
                        Zlib in-memory and local browser cache for synthesized audio briefings and KaTeX formulas.
                      </div>
                    </div>
                    <button type="button" class="pf-btn pf-btn-secondary pf-btn-sm" style="color: var(--pf-danger); border-color: rgba(225,29,72,0.3);" onclick="ProfFebUI.settings.clearCache()">
                      Clear Cache
                    </button>
                  </div>
                </div>

                <!-- Appearance Preference -->
                <div style="display: flex; justify-content: space-between; align-items: center;">
                  <div>
                    <div style="font-size: 14px; font-weight: 600; color: var(--pf-text-primary);">Theme Mode</div>
                    <div style="font-size: 12px; color: var(--pf-text-muted);">Toggle between warm light editorial paper and dark midnight</div>
                  </div>
                  <button type="button" class="pf-btn pf-btn-secondary pf-btn-sm" onclick="ProfFebUI.theme.toggle()">
                    <span class="pf-theme-toggle-label">${ProfFebUI.theme.get() === 'dark' ? 'Light Mode' : 'Dark Mode'}</span>
                  </button>
                </div>

                <!-- Engine Status Summary -->
                <div style="font-size: 12px; color: var(--pf-text-muted); padding-top: 0.5rem; border-top: 1px solid var(--pf-border-subtle); display: flex; justify-content: space-between;">
                  <span>ProfFeb Research OS v2.0.0</span>
                  <span>7 Neural Engines Operational</span>
                </div>
              </div>
            </div>
          `;
          document.body.appendChild(modal);
          modal.addEventListener('click', (e) => {
            if (e.target === modal) ProfFebUI.settings.close();
          });
        }

        ProfFebUI.zotero.updateStatusBadge();
        modal.classList.add('active');
        if (window.lucide) window.lucide.createIcons();
      },
      close: function () {
        const modal = document.getElementById('pf-settings-modal');
        if (modal) modal.classList.remove('active');
      },
      clearCache: function () {
        if (confirm("Reset and clear audio synthesis cache? Your saved papers and database entries remain safe.")) {
          try {
            localStorage.removeItem('proffeb_audio_cache');
            localStorage.removeItem('proffeb_recent_papers');
          } catch (e) {}

          ProfFebUI.toast({
            title: "Audio Cache Cleared",
            message: "Temporary audio buffers reset. Ready for clean neural synthesis.",
            type: "success"
          });
          ProfFebUI.settings.close();
        }
      }
    },

    // 4. Zotero Account Integration Controller
    zotero: {
      getCredentials: function () {
        return {
          id: localStorage.getItem('zam_zotero_id') || '',
          key: localStorage.getItem('zam_zotero_key') || '',
          type: localStorage.getItem('zam_zotero_type') || 'user'
        };
      },
      saveCredentials: async function (id, key, type = 'user') {
        localStorage.setItem('zam_zotero_id', id);
        if (key) localStorage.setItem('zam_zotero_key', key);
        localStorage.setItem('zam_zotero_type', type);

        // If authenticated with Supabase, persist to backend profile
        if (window.ProfFebAuth && window.ProfFebAuth.token) {
          try {
            await fetch('/api/user/zotero', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({
                library_id: id,
                api_key: key || undefined,
                library_type: type
              })
            });
          } catch (e) {
            console.warn('Could not sync Zotero credentials to cloud profile:', e);
          }
        }
        this.updateStatusBadge();
        window.dispatchEvent(new CustomEvent('proffeb-zotero-updated', { detail: { id, type } }));
      },
      clearCredentials: function () {
        localStorage.removeItem('zam_zotero_id');
        localStorage.removeItem('zam_zotero_key');
        localStorage.removeItem('zam_zotero_type');
        ProfFebUI.toast({
          title: 'Zotero Disconnected',
          message: 'Saved Zotero library credentials have been cleared.',
          type: 'info'
        });
        this.updateStatusBadge();
        this.close();
        window.dispatchEvent(new CustomEvent('proffeb-zotero-updated', { detail: { id: '', type: 'user' } }));
      },
      updateStatusBadge: function () {
        const creds = this.getCredentials();
        const badge = document.getElementById('pf-zotero-status-indicator');
        if (badge) {
          if (creds.id) {
            badge.innerHTML = `<span class="pf-badge pf-badge-emerald" style="font-size:10px;">Connected (ID: ${creds.id})</span>`;
          } else {
            badge.innerHTML = `<span class="pf-badge pf-badge-amber" style="font-size:10px;">Not Configured</span>`;
          }
        }
      },
      toggleKeyVisibility: function () {
        const input = document.getElementById('pf-zotero-modal-key');
        const btn = document.getElementById('pf-zotero-toggle-key-btn');
        if (!input || !btn) return;
        if (input.type === 'password') {
          input.type = 'text';
          btn.textContent = 'Hide';
        } else {
          input.type = 'password';
          btn.textContent = 'Show';
        }
      },
      testConnection: async function () {
        const idInput = document.getElementById('pf-zotero-modal-id');
        const keyInput = document.getElementById('pf-zotero-modal-key');
        const typeInput = document.getElementById('pf-zotero-modal-type');
        const statusBox = document.getElementById('pf-zotero-modal-alert');
        const btn = document.getElementById('pf-zotero-test-btn');

        const id = (idInput ? idInput.value : '').trim();
        const key = (keyInput ? keyInput.value : '').trim();
        const type = (typeInput ? typeInput.value : 'user').trim();

        if (!id || !key) {
          if (statusBox) {
            statusBox.style.display = 'block';
            statusBox.style.background = 'var(--pf-danger-subtle)';
            statusBox.style.color = 'var(--pf-danger)';
            statusBox.style.border = '1px solid rgba(225,29,72,0.3)';
            statusBox.innerHTML = '<strong>Missing details:</strong> Please enter both your Zotero User ID and Private API Key.';
          }
          return;
        }

        if (btn) {
          btn.disabled = true;
          btn.textContent = 'Testing...';
        }

        try {
          const res = await fetch('/api/settings/test-zotero', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ library_id: id, api_key: key, library_type: type })
          });
          const data = await res.json();
          if (statusBox) {
            statusBox.style.display = 'block';
            if (data.success) {
              statusBox.style.background = 'var(--pf-success-subtle)';
              statusBox.style.color = 'var(--pf-success)';
              statusBox.style.border = '1px solid rgba(16,185,129,0.3)';
              statusBox.innerHTML = `<strong>Connected!</strong> ${data.message || 'Zotero credentials verified with library read access.'}`;
            } else {
              statusBox.style.background = 'var(--pf-danger-subtle)';
              statusBox.style.color = 'var(--pf-danger)';
              statusBox.style.border = '1px solid rgba(225,29,72,0.3)';
              statusBox.innerHTML = `<strong>Connection Failed:</strong> ${data.message || 'Invalid User ID or API Key. Check permissions.'}`;
            }
          }
        } catch (err) {
          if (statusBox) {
            statusBox.style.display = 'block';
            statusBox.style.background = 'var(--pf-danger-subtle)';
            statusBox.style.color = 'var(--pf-danger)';
            statusBox.style.border = '1px solid rgba(225,29,72,0.3)';
            statusBox.innerHTML = `<strong>Network Error:</strong> ${err.message}`;
          }
        } finally {
          if (btn) {
            btn.disabled = false;
            btn.textContent = 'Test Connection';
          }
        }
      },
      saveAndSync: async function () {
        const idInput = document.getElementById('pf-zotero-modal-id');
        const keyInput = document.getElementById('pf-zotero-modal-key');
        const typeInput = document.getElementById('pf-zotero-modal-type');
        const statusBox = document.getElementById('pf-zotero-modal-alert');
        const saveBtn = document.getElementById('pf-zotero-save-btn');

        const id = (idInput ? idInput.value : '').trim();
        const key = (keyInput ? keyInput.value : '').trim();
        const type = (typeInput ? typeInput.value : 'user').trim();

        if (!id) {
          if (statusBox) {
            statusBox.style.display = 'block';
            statusBox.style.background = 'var(--pf-danger-subtle)';
            statusBox.style.color = 'var(--pf-danger)';
            statusBox.innerHTML = 'Please enter your numeric Zotero User ID.';
          }
          return;
        }

        if (saveBtn) {
          saveBtn.disabled = true;
          saveBtn.textContent = 'Saving...';
        }

        await this.saveCredentials(id, key, type);

        ProfFebUI.toast({
          title: 'Zotero Connected',
          message: `Saved Library ID: ${id}. Initializing sync...`,
          type: 'success'
        });

        this.close();

        // If on /app and triggerZoteroSync exists, trigger it!
        if (typeof window.triggerZoteroSync === 'function') {
          window.triggerZoteroSync();
        }
      },
      open: function () {
        let modal = document.getElementById('pf-zotero-modal');
        const creds = this.getCredentials();

        if (!modal) {
          modal = document.createElement('div');
          modal.id = 'pf-zotero-modal';
          modal.className = 'pf-modal-overlay';
          modal.innerHTML = `
            <div class="pf-modal" style="max-width: 540px;">
              <div style="padding: 1.25rem 1.5rem; border-bottom: 1px solid var(--pf-border-subtle); display: flex; align-items: center; justify-content: space-between;">
                <div style="display: flex; align-items: center; gap: 0.75rem;">
                  <div style="width: 36px; height: 36px; border-radius: 10px; background: var(--pf-engine-studio-bg); display: flex; align-items: center; justify-content: center; color: var(--pf-engine-studio); border: 1px solid var(--pf-engine-studio-border);">
                    <i data-lucide="library" style="width: 20px; height: 20px;"></i>
                  </div>
                  <div>
                    <h3 style="font-size: 16px; font-weight: 700; margin: 0; color: var(--pf-text-primary);">Connect Zotero Reference Library</h3>
                    <p style="font-size: 12px; margin: 0; color: var(--pf-text-muted);">Sync manuscripts, metadata & PDFs to your account</p>
                  </div>
                </div>
                <button type="button" class="pf-btn pf-btn-ghost pf-btn-sm" onclick="ProfFebUI.zotero.close()">✕</button>
              </div>

              <div style="padding: 1.5rem; display: flex; flex-direction: column; gap: 1.125rem;">
                
                <!-- Quick Instructions Banner -->
                <div style="padding: 0.875rem 1rem; border-radius: 12px; background: var(--pf-bg-surface-elevated); border: 1px solid var(--pf-border-subtle); font-size: 12px; line-height: 1.5; color: var(--pf-text-secondary);">
                  <div style="font-weight: 700; color: var(--pf-text-primary); margin-bottom: 4px; display: flex; align-items: center; gap: 6px;">
                    <i data-lucide="info" style="width: 14px; height: 14px; color: var(--pf-primary);"></i>
                    How to find your Zotero credentials:
                  </div>
                  <ol style="margin: 0; padding-left: 1.25rem;">
                    <li>Open <a href="https://www.zotero.org/settings/keys" target="_blank" style="color: var(--pf-primary); font-weight: 600; text-decoration: underline;">zotero.org/settings/keys</a> in a new tab.</li>
                    <li>Copy your numeric <strong>User ID</strong> (shown under "Your User ID for API calls").</li>
                    <li>Click <strong>Create new private key</strong> & ensure <strong>Allow library access</strong> and <strong>Allow file read</strong> are checked.</li>
                  </ol>
                </div>

                <!-- Live alert box -->
                <div id="pf-zotero-modal-alert" style="display: none; padding: 0.75rem 1rem; border-radius: 10px; font-size: 12px;"></div>

                <!-- User ID Field -->
                <div>
                  <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px;">
                    <label style="font-size: 12px; font-weight: 700; color: var(--pf-text-primary);">Zotero User ID (Library ID)</label>
                    <a href="https://www.zotero.org/settings/keys" target="_blank" style="font-size: 11px; color: var(--pf-primary); text-decoration: none;">Find ID &rarr;</a>
                  </div>
                  <input id="pf-zotero-modal-id" type="text" placeholder="e.g. 1234567" value="${creds.id}" style="width: 100%; font-family: var(--pf-font-mono); font-size: 13px; padding: 8px 12px; border-radius: 10px; border: 1px solid var(--pf-border-default); background: var(--pf-bg-surface); color: var(--pf-text-primary); outline: none;">
                </div>

                <!-- API Key Field -->
                <div>
                  <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px;">
                    <label style="font-size: 12px; font-weight: 700; color: var(--pf-text-primary);">Private API Key</label>
                    <a href="https://www.zotero.org/settings/keys/new" target="_blank" style="font-size: 11px; color: var(--pf-primary); text-decoration: none;">Generate Key &rarr;</a>
                  </div>
                  <div style="display: flex; gap: 8px;">
                    <input id="pf-zotero-modal-key" type="password" placeholder="e.g. 3jK8nAbCdEfGhIjK..." value="${creds.key}" style="flex: 1; font-family: var(--pf-font-mono); font-size: 13px; padding: 8px 12px; border-radius: 10px; border: 1px solid var(--pf-border-default); background: var(--pf-bg-surface); color: var(--pf-text-primary); outline: none;">
                    <button id="pf-zotero-toggle-key-btn" type="button" class="pf-btn pf-btn-secondary pf-btn-sm" onclick="ProfFebUI.zotero.toggleKeyVisibility()">Show</button>
                  </div>
                </div>

                <!-- Library Type Field -->
                <div>
                  <label style="font-size: 12px; font-weight: 700; color: var(--pf-text-primary); display: block; margin-bottom: 4px;">Library Type</label>
                  <select id="pf-zotero-modal-type" style="width: 100%; font-size: 13px; padding: 8px 12px; border-radius: 10px; border: 1px solid var(--pf-border-default); background: var(--pf-bg-surface); color: var(--pf-text-primary); outline: none;">
                    <option value="user" ${creds.type === 'user' ? 'selected' : ''}>Personal Library (user)</option>
                    <option value="group" ${creds.type === 'group' ? 'selected' : ''}>Group / Lab Library (group)</option>
                  </select>
                </div>

                <!-- Action Buttons -->
                <div style="display: flex; align-items: center; justify-content: space-between; gap: 10px; margin-top: 6px; padding-top: 1rem; border-top: 1px solid var(--pf-border-subtle);">
                  <div style="display: flex; gap: 8px;">
                    <button id="pf-zotero-test-btn" type="button" class="pf-btn pf-btn-secondary pf-btn-sm" onclick="ProfFebUI.zotero.testConnection()">
                      Test Connection
                    </button>
                    ${creds.id ? `<button type="button" class="pf-btn pf-btn-ghost pf-btn-sm" style="color: var(--pf-danger);" onclick="ProfFebUI.zotero.clearCredentials()">Disconnect</button>` : ''}
                  </div>
                  <button id="pf-zotero-save-btn" type="button" class="pf-btn pf-btn-primary pf-btn-sm" onclick="ProfFebUI.zotero.saveAndSync()" style="font-weight: 700;">
                    Save & Sync Now
                  </button>
                </div>

              </div>
            </div>
          `;
          document.body.appendChild(modal);
          modal.addEventListener('click', (e) => {
            if (e.target === modal) ProfFebUI.zotero.close();
          });
        } else {
          // Pre-populate latest values
          const idInput = document.getElementById('pf-zotero-modal-id');
          const keyInput = document.getElementById('pf-zotero-modal-key');
          const typeInput = document.getElementById('pf-zotero-modal-type');
          if (idInput) idInput.value = creds.id;
          if (keyInput) keyInput.value = creds.key;
          if (typeInput) typeInput.value = creds.type;
        }

        modal.classList.add('active');
        if (window.lucide) window.lucide.createIcons();
      },
      close: function () {
        const modal = document.getElementById('pf-zotero-modal');
        if (modal) modal.classList.remove('active');
      }
    },

    // 4. Collapsible Sidebar Controller
    sidebar: {
      toggle: function () {
        const sidebar = document.querySelector('.pf-sidebar');
        if (!sidebar) return;
        const isCollapsed = sidebar.classList.toggle('collapsed');
        localStorage.setItem('proffeb_sidebar_collapsed', isCollapsed ? 'true' : 'false');
      },
      toggleMobile: function () {
        const sidebar = document.querySelector('.pf-sidebar');
        if (!sidebar) return;
        sidebar.classList.toggle('mobile-open');
      },
      init: function () {
        const sidebar = document.querySelector('.pf-sidebar');
        if (!sidebar) return;
        const saved = localStorage.getItem('proffeb_sidebar_collapsed');
        if (saved === 'true') {
          sidebar.classList.add('collapsed');
        }
      }
    },

    // 5. Global Command Palette (Cmd/Ctrl + K)
    palette: {
      open: function () {
        let palette = document.getElementById('pf-command-palette');
        if (!palette) {
          palette = document.createElement('div');
          palette.id = 'pf-command-palette';
          palette.className = 'pf-modal-overlay';
          palette.innerHTML = `
            <div class="pf-modal" style="max-width: 520px;">
              <div style="padding: 0.875rem 1rem; border-bottom: 1px solid var(--pf-border-subtle); display: flex; align-items: center; gap: 0.75rem;">
                <i data-lucide="search" style="color: var(--pf-text-muted); width: 18px; height: 18px;"></i>
                <input id="pf-palette-search" type="text" placeholder="Jump to an engine or action... (Esc to close)" style="border: none; background: transparent; width: 100%; font-size: 14px; color: var(--pf-text-primary); outline: none;">
                <kbd style="font-size: 10px; font-family: var(--pf-font-mono); padding: 2px 6px; border-radius: 4px; background: var(--pf-bg-surface-elevated); color: var(--pf-text-muted);">ESC</kbd>
              </div>
              <div id="pf-palette-results" style="max-height: 340px; overflow-y: auto; padding: 0.5rem;">
                <div style="font-size: 11px; font-weight: 700; color: var(--pf-text-muted); text-transform: uppercase; padding: 0.375rem 0.625rem;">Research Engines</div>
                <a href="/app" class="pf-nav-item" style="margin-bottom: 2px;">
                  <span class="pf-nav-icon-wrap" style="background: var(--pf-engine-studio-bg); color: var(--pf-engine-studio);"><i data-lucide="headphones" style="width: 15px; height: 15px;"></i></span>
                  <div style="flex: 1;"><div style="font-weight: 600;">01. Research Studio</div><div style="font-size: 11px; color: var(--pf-text-muted);">Spoken audio & math deconstruction</div></div>
                </a>
                <a href="/conferences" class="pf-nav-item" style="margin-bottom: 2px;">
                  <span class="pf-nav-icon-wrap" style="background: var(--pf-engine-scout-bg); color: var(--pf-engine-scout);"><i data-lucide="calendar" style="width: 15px; height: 15px;"></i></span>
                  <div style="flex: 1;"><div style="font-weight: 600;">02. Conference Scout</div><div style="font-size: 11px; color: var(--pf-text-muted);">CORE A* rankings & travel grant deadlines</div></div>
                </a>
                <a href="/radar" class="pf-nav-item" style="margin-bottom: 2px;">
                  <span class="pf-nav-icon-wrap" style="background: var(--pf-engine-radar-bg); color: var(--pf-engine-radar);"><i data-lucide="radar" style="width: 15px; height: 15px;"></i></span>
                  <div style="flex: 1;"><div style="font-weight: 600;">03. Novelty Radar</div><div style="font-size: 11px; color: var(--pf-text-muted);">Literature gap analysis & competitor matrix</div></div>
                </a>
                <a href="/reviewer" class="pf-nav-item" style="margin-bottom: 2px;">
                  <span class="pf-nav-icon-wrap" style="background: var(--pf-engine-reviewer-bg); color: var(--pf-engine-reviewer);"><i data-lucide="shield-alert" style="width: 15px; height: 15px;"></i></span>
                  <div style="flex: 1;"><div style="font-weight: 600;">04. AI Reviewer #2</div><div style="font-size: 11px; color: var(--pf-text-muted);">Adversarial manuscript audit & rebuttal coach</div></div>
                </a>
                <a href="/grants" class="pf-nav-item" style="margin-bottom: 2px;">
                  <span class="pf-nav-icon-wrap" style="background: var(--pf-engine-grants-bg); color: var(--pf-engine-grants);"><i data-lucide="badge-dollar-sign" style="width: 15px; height: 15px;"></i></span>
                  <div style="flex: 1;"><div style="font-weight: 600;">05. Funding Radar</div><div style="font-size: 11px; color: var(--pf-text-muted);">Doctoral fellowships & travel stipends</div></div>
                </a>
                <a href="/lab-connector" class="pf-nav-item" style="margin-bottom: 2px;">
                  <span class="pf-nav-icon-wrap" style="background: var(--pf-engine-lab-bg); color: var(--pf-engine-lab);"><i data-lucide="building-2" style="width: 15px; height: 15px;"></i></span>
                  <div style="flex: 1;"><div style="font-weight: 600;">06. Lab Connector</div><div style="font-size: 11px; color: var(--pf-text-muted);">Postdoc & visiting researcher matching</div></div>
                </a>
                <a href="/agent" class="pf-nav-item" style="margin-bottom: 2px;">
                  <span class="pf-nav-icon-wrap" style="background: var(--pf-engine-copilot-bg); color: var(--pf-engine-copilot);"><i data-lucide="bot" style="width: 15px; height: 15px;"></i></span>
                  <div style="flex: 1;"><div style="font-weight: 600;">07. Academic Co-Pilot</div><div style="font-size: 11px; color: var(--pf-text-muted);">Autonomous application dispatch & GitHub twin</div></div>
                </a>
                <div style="font-size: 11px; font-weight: 700; color: var(--pf-text-muted); text-transform: uppercase; padding: 0.625rem 0.625rem 0.375rem; border-top: 1px solid var(--pf-border-subtle); margin-top: 4px;">Integrations & Preferences</div>
                <button type="button" onclick="ProfFebUI.palette.close(); ProfFebUI.zotero.open();" class="pf-nav-item" style="width: 100%; border: none; background: transparent; cursor: pointer; text-align: left; margin-bottom: 2px;">
                  <span class="pf-nav-icon-wrap" style="background: var(--pf-engine-studio-bg); color: var(--pf-engine-studio);"><i data-lucide="library" style="width: 15px; height: 15px;"></i></span>
                  <div style="flex: 1;"><div style="font-weight: 600;">Connect Zotero Reference Library</div><div style="font-size: 11px; color: var(--pf-text-muted);">Setup personal or lab Zotero credentials & API sync</div></div>
                </button>
                <button type="button" onclick="ProfFebUI.palette.close(); ProfFebUI.settings.open();" class="pf-nav-item" style="width: 100%; border: none; background: transparent; cursor: pointer; text-align: left;">
                  <span class="pf-nav-icon-wrap" style="background: var(--pf-bg-surface-elevated); color: var(--pf-text-secondary);"><i data-lucide="settings" style="width: 15px; height: 15px;"></i></span>
                  <div style="flex: 1;"><div style="font-weight: 600;">Workstation Settings</div><div style="font-size: 11px; color: var(--pf-text-muted);">Audio cache controls & appearance mode</div></div>
                </button>
              </div>
            </div>
          `;
          document.body.appendChild(palette);
          palette.addEventListener('click', (e) => {
            if (e.target === palette) ProfFebUI.palette.close();
          });
        }

        palette.classList.add('active');
        const input = document.getElementById('pf-palette-search');
        if (input) {
          input.value = '';
          input.focus();
        }
        if (window.lucide) window.lucide.createIcons();
      },
      close: function () {
        const palette = document.getElementById('pf-command-palette');
        if (palette) palette.classList.remove('active');
      }
    },

    // 6. Global Init
    init: function () {
      this.theme.init();
      this.sidebar.init();

      // Keyboard listener for Cmd+K and Esc
      document.addEventListener('keydown', (e) => {
        if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
          e.preventDefault();
          ProfFebUI.palette.open();
        } else if (e.key === 'Escape') {
          ProfFebUI.palette.close();
          ProfFebUI.settings.close();
        }
      });

      // Auto-render Lucide icons on load
      if (window.lucide && typeof window.lucide.createIcons === 'function') {
        window.lucide.createIcons();
      }
    }
  };

  window.ProfFebUI = ProfFebUI;
  document.addEventListener('DOMContentLoaded', () => ProfFebUI.init());
})();
