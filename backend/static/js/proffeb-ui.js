/**
 * ProfFeb UI Engine & Component Library
 * Powers Theme Switcher (Light/Dark), Command Palette (Cmd+K),
 * Toast Notifications, Sidebar Collapse, and Breadcrumbs.
 */

(function () {
  'use strict';

  const ProfFebUI = {
    // 1. Theme Management
    theme: {
      get: function () {
        const stored = localStorage.getItem('proffeb_theme');
        if (stored) return stored;
        return window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'dark';
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
        // Update all theme toggle button icons if present
        document.querySelectorAll('.pf-theme-toggle-icon').forEach(el => {
          el.innerHTML = theme === 'dark' ? '☀️' : '🌙';
        });
        document.querySelectorAll('.pf-theme-toggle-label').forEach(el => {
          el.textContent = theme === 'dark' ? 'Light Mode' : 'Dark Mode';
        });
        window.dispatchEvent(new CustomEvent('proffeb-theme-changed', { detail: { theme } }));
      },
      toggle: function () {
        const current = this.get();
        const next = current === 'dark' ? 'light' : 'dark';
        this.set(next);
        ProfFebUI.toast({
          title: `Theme Switched`,
          message: `Switched to ${next === 'dark' ? 'Dark' : 'Light'} theme.`,
          type: 'info',
          duration: 2500
        });
      },
      init: function () {
        this.set(this.get());
      }
    },

    // 2. Toast Notification Hub
    toast: function ({ title = '', message = '', type = 'info', duration = 4000 } = {}) {
      let container = document.getElementById('pf-toast-container');
      if (!container) {
        container = document.createElement('div');
        container.id = 'pf-toast-container';
        document.body.appendChild(container);
      }

      const icons = {
        success: '✓',
        error: '✕',
        warning: '⚠',
        info: 'ℹ'
      };

      const iconColors = {
        success: 'var(--pf-success)',
        error: 'var(--pf-danger)',
        warning: 'var(--pf-warning)',
        info: 'var(--pf-info)'
      };

      const toastEl = document.createElement('div');
      toastEl.className = 'pf-toast';
      toastEl.setAttribute('role', 'status');
      toastEl.setAttribute('aria-live', 'polite');
      toastEl.innerHTML = `
        <div class="pf-toast-icon" style="color: ${iconColors[type] || iconColors.info}; font-weight: bold;">
          ${icons[type] || icons.info}
        </div>
        <div style="flex: 1; min-width: 0;">
          ${title ? `<div class="pf-toast-title">${title}</div>` : ''}
          <div class="pf-toast-msg">${message}</div>
        </div>
        <button type="button" class="pf-btn-ghost pf-btn-sm" style="padding: 2px 6px; font-size: 11px; opacity: 0.6;" onclick="this.parentElement.remove()">✕</button>
      `;

      container.appendChild(toastEl);
      requestAnimationFrame(() => {
        toastEl.classList.add('pf-toast-visible');
      });

      if (duration > 0) {
        setTimeout(() => {
          toastEl.classList.remove('pf-toast-visible');
          setTimeout(() => toastEl.remove(), 250);
        }, duration);
      }
    },

    // 3. Global Command Palette (Cmd+K / Ctrl+K)
    commandPalette: {
      items: [
        { title: 'Overview & System Story', category: 'Navigation', url: '/', icon: '⊞', shortcut: '0' },
        { title: 'Research Studio (Briefings & Audio)', category: 'Engines', url: '/app', icon: '🎙️', shortcut: '1' },
        { title: 'Conference & Event Scout', category: 'Engines', url: '/conferences', icon: '🌐', shortcut: '2' },
        { title: 'Novelty & Research Gap Radar', category: 'Engines', url: '/radar', icon: '🔬', shortcut: '3' },
        { title: 'AI Reviewer #2 Simulator', category: 'Engines', url: '/reviewer', icon: '⚖️', shortcut: '4' },
        { title: 'Funding & Travel Grants Radar', category: 'Engines', url: '/grants', icon: '💰', shortcut: '5' },
        { title: 'Industry Lab Connector', category: 'Engines', url: '/lab-connector', icon: '🏢', shortcut: '6' },
        { title: 'Academic Co-Pilot & Dossier', category: 'Engines', url: '/agent', icon: '🧠', shortcut: '7' },
        { title: 'Toggle Light / Dark Theme', category: 'Actions', action: () => ProfFebUI.theme.toggle(), icon: '🌓', shortcut: 'T' },
        { title: 'View API System Health', category: 'Actions', url: '/api/health', icon: '💚', shortcut: 'H' }
      ],
      open: function () {
        const modal = document.getElementById('pf-command-modal');
        if (modal) {
          modal.classList.add('pf-modal-open');
          const input = modal.querySelector('.pf-command-input');
          if (input) {
            input.value = '';
            input.focus();
            ProfFebUI.commandPalette.renderItems('');
          }
        }
      },
      close: function () {
        const modal = document.getElementById('pf-command-modal');
        if (modal) modal.classList.remove('pf-modal-open');
      },
      renderItems: function (query = '') {
        const list = document.getElementById('pf-command-list');
        if (!list) return;

        const filtered = ProfFebUI.commandPalette.items.filter(item =>
          item.title.toLowerCase().includes(query.toLowerCase()) ||
          item.category.toLowerCase().includes(query.toLowerCase())
        );

        if (filtered.length === 0) {
          list.innerHTML = `<div style="padding: 20px; text-align: center; color: var(--pf-text-muted); font-size: 13px;">No matching engines or commands found.</div>`;
          return;
        }

        list.innerHTML = filtered.map((item, idx) => `
          <div class="pf-command-item ${idx === 0 ? 'pf-command-active' : ''}" data-idx="${idx}" onclick="ProfFebUI.commandPalette.select(${idx})">
            <div style="display: flex; align-items: center; gap: 10px;">
              <span style="font-size: 16px;">${item.icon}</span>
              <div>
                <div style="font-weight: 600;">${item.title}</div>
                <div style="font-size: 11px; color: var(--pf-text-muted);">${item.category}</div>
              </div>
            </div>
            ${item.shortcut ? `<span class="pf-badge pf-badge-emerald" style="font-family: var(--pf-font-mono); font-size: 10px;">${item.shortcut}</span>` : ''}
          </div>
        `).join('');
      },
      select: function (idx) {
        const item = ProfFebUI.commandPalette.items[idx];
        if (!item) return;
        this.close();
        if (item.action) {
          item.action();
        } else if (item.url) {
          window.location.href = item.url;
        }
      },
      init: function () {
        // Inject modal HTML if not already in document
        if (!document.getElementById('pf-command-modal')) {
          const modal = document.createElement('div');
          modal.id = 'pf-command-modal';
          modal.innerHTML = `
            <div class="pf-command-box" onclick="event.stopPropagation()">
              <div class="pf-command-input-row">
                <span style="font-size: 16px; opacity: 0.6;">🔍</span>
                <input type="text" class="pf-command-input" placeholder="Type a command or jump to engine... (Esc to close)" autocomplete="off" spellcheck="false">
                <span class="pf-badge" style="font-family: var(--pf-font-mono); font-size: 10px; opacity: 0.6;">ESC</span>
              </div>
              <div id="pf-command-list" class="pf-command-list"></div>
            </div>
          `;
          modal.addEventListener('click', () => ProfFebUI.commandPalette.close());
          document.body.appendChild(modal);

          const input = modal.querySelector('.pf-command-input');
          input.addEventListener('input', (e) => {
            ProfFebUI.commandPalette.renderItems(e.target.value);
          });
          input.addEventListener('keydown', (e) => {
            if (e.key === 'Escape') ProfFebUI.commandPalette.close();
            if (e.key === 'Enter') {
              const active = modal.querySelector('.pf-command-item.pf-command-active');
              if (active) {
                const idx = parseInt(active.getAttribute('data-idx'), 10);
                ProfFebUI.commandPalette.select(idx);
              }
            }
          });
        }

        // Global hotkey listener
        window.addEventListener('keydown', (e) => {
          if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
            e.preventDefault();
            ProfFebUI.commandPalette.open();
          }
        });
      }
    },

    // 4. Sidebar Controller
    sidebar: {
      isCollapsed: function () {
        return localStorage.getItem('proffeb_sidebar_collapsed') === 'true';
      },
      toggle: function () {
        const sidebar = document.getElementById('pf-app-sidebar');
        if (!sidebar) return;
        const collapsed = sidebar.classList.toggle('pf-sidebar-collapsed');
        localStorage.setItem('proffeb_sidebar_collapsed', collapsed ? 'true' : 'false');
      },
      init: function () {
        const sidebar = document.getElementById('pf-app-sidebar');
        if (sidebar && this.isCollapsed()) {
          sidebar.classList.add('pf-sidebar-collapsed');
        }
      }
    },

    // 5. Initialize full suite
    init: function () {
      this.theme.init();
      this.commandPalette.init();
      this.sidebar.init();
    }
  };

  // Expose globally
  window.ProfFebUI = ProfFebUI;

  // Run on DOM loaded
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => ProfFebUI.init());
  } else {
    ProfFebUI.init();
  }
})();
