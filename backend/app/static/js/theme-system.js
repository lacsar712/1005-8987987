(function () {
    const STORAGE_KEY = 'album_theme_settings';
    const PRESET_KEY = 'album_theme_presets';

    const ACCENT_COLORS = {
        blue: { base: '#3b82f6', hover: '#2563eb', light: '#dbeafe' },
        green: { base: '#10b981', hover: '#059669', light: '#d1fae5' },
        purple: { base: '#8b5cf6', hover: '#7c3aed', light: '#ede9fe' },
        orange: { base: '#f97316', hover: '#ea580c', light: '#ffedd5' },
    };

    const MODE_PRESETS = {
        light: {
            '--color-bg': '#f9fafb',
            '--color-card': '#ffffff',
            '--color-card-border': '#f3f4f6',
            '--color-text': '#1f2937',
            '--color-text-secondary': '#6b7280',
            '--color-text-muted': '#9ca3af',
            '--color-danger': '#ef4444',
            '--color-success': '#10b981',
            '--color-warning': '#f59e0b',
            '--color-nav-bg': '#ffffff',
            '--color-nav-text': '#1f2937',
            '--color-nav-border': '#e5e7eb',
            '--color-footer-bg': '#ffffff',
            '--color-footer-border': '#f3f4f6',
            '--color-overlay': 'rgba(0, 0, 0, 0.8)',
            '--color-toolbar-bg': 'rgba(0, 0, 0, 0.6)',
            '--color-toolbar-text': '#ffffff',
        },
        dark: {
            '--color-bg': '#111827',
            '--color-card': '#1f2937',
            '--color-card-border': '#374151',
            '--color-text': '#f9fafb',
            '--color-text-secondary': '#d1d5db',
            '--color-text-muted': '#9ca3af',
            '--color-danger': '#f87171',
            '--color-success': '#34d399',
            '--color-warning': '#fbbf24',
            '--color-nav-bg': '#1f2937',
            '--color-nav-text': '#f9fafb',
            '--color-nav-border': '#374151',
            '--color-footer-bg': '#1f2937',
            '--color-footer-border': '#374151',
            '--color-overlay': 'rgba(0, 0, 0, 0.92)',
            '--color-toolbar-bg': 'rgba(31, 41, 55, 0.85)',
            '--color-toolbar-text': '#f9fafb',
        },
    };

    const DEFAULT_SETTINGS = {
        mode: 'light',
        accent: 'blue',
        custom: {
            '--color-bg': null,
            '--color-card': null,
            '--radius-base': '8px',
            '--font-scale': '1',
        },
        activePreset: null,
    };

    function loadSettings() {
        try {
            const raw = localStorage.getItem(STORAGE_KEY);
            if (!raw) return JSON.parse(JSON.stringify(DEFAULT_SETTINGS));
            const parsed = JSON.parse(raw);
            return Object.assign(JSON.parse(JSON.stringify(DEFAULT_SETTINGS)), parsed);
        } catch (e) {
            return JSON.parse(JSON.stringify(DEFAULT_SETTINGS));
        }
    }

    function saveSettings(settings) {
        localStorage.setItem(STORAGE_KEY, JSON.stringify(settings));
    }

    function loadPresets() {
        try {
            const raw = localStorage.getItem(PRESET_KEY);
            return raw ? JSON.parse(raw) : {};
        } catch (e) {
            return {};
        }
    }

    function savePresets(presets) {
        localStorage.setItem(PRESET_KEY, JSON.stringify(presets));
    }

    function resolveEffectiveMode(settings) {
        if (settings.mode === 'system') {
            return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
        }
        return settings.mode;
    }

    function hexToRgba(hex, alpha) {
        const clean = hex.replace('#', '');
        const r = parseInt(clean.substring(0, 2), 16);
        const g = parseInt(clean.substring(2, 4), 16);
        const b = parseInt(clean.substring(4, 6), 16);
        return `rgba(${r}, ${g}, ${b}, ${alpha})`;
    }

    function lightenOrDarken(hex, amount) {
        const clean = hex.replace('#', '');
        const r = Math.max(0, Math.min(255, parseInt(clean.substring(0, 2), 16) + amount));
        const g = Math.max(0, Math.min(255, parseInt(clean.substring(2, 4), 16) + amount));
        const b = Math.max(0, Math.min(255, parseInt(clean.substring(4, 6), 16) + amount));
        return '#' + [r, g, b].map(c => c.toString(16).padStart(2, '0')).join('');
    }

    function applyTheme(settings) {
        const effectiveMode = resolveEffectiveMode(settings);
        const baseVars = MODE_PRESETS[effectiveMode];
        const accent = ACCENT_COLORS[settings.accent] || ACCENT_COLORS.blue;

        const root = document.documentElement;
        const body = document.body;

        Object.keys(baseVars).forEach(key => {
            root.style.setProperty(key, baseVars[key]);
        });

        root.style.setProperty('--color-accent', accent.base);
        root.style.setProperty('--color-accent-hover', accent.hover);
        root.style.setProperty('--color-accent-light', accent.light);

        let fontScale = 1;
        if (settings.custom) {
            if (settings.custom['--color-bg']) {
                root.style.setProperty('--color-bg', settings.custom['--color-bg']);
            }
            if (settings.custom['--color-card']) {
                root.style.setProperty('--color-card', settings.custom['--color-card']);
                const cardBorder = lightenOrDarken(settings.custom['--color-card'], effectiveMode === 'dark' ? 20 : -20);
                root.style.setProperty('--color-card-border', cardBorder);
                root.style.setProperty('--color-nav-bg', settings.custom['--color-card']);
                root.style.setProperty('--color-footer-bg', settings.custom['--color-card']);
                root.style.setProperty('--color-nav-border', cardBorder);
                root.style.setProperty('--color-footer-border', cardBorder);
            }
            if (settings.custom['--radius-base']) {
                const r = settings.custom['--radius-base'];
                root.style.setProperty('--radius-base', r);
                root.style.setProperty('--radius-lg', (parseInt(r) + 4) + 'px');
            }
            if (settings.custom['--font-scale']) {
                fontScale = parseFloat(settings.custom['--font-scale']) || 1;
                root.style.setProperty('--font-scale', settings.custom['--font-scale']);
            }
        }

        root.style.fontSize = (16 * fontScale) + 'px';

        updateThemeIcon(effectiveMode, settings.mode);
        updateActiveModeUI(settings.mode);
        updateActiveAccentUI(settings.accent);
        updateWorkshopUI(settings);
        applyViewerOverrides(effectiveMode);
        applyGlobalClassOverrides(effectiveMode);
    }

    function updateThemeIcon(effectiveMode, rawMode) {
        const sun = document.getElementById('theme-icon-sun');
        const moon = document.getElementById('theme-icon-moon');
        const auto = document.getElementById('theme-icon-auto');
        if (!sun || !moon || !auto) return;
        sun.classList.add('hidden');
        moon.classList.add('hidden');
        auto.classList.add('hidden');
        if (rawMode === 'system') {
            auto.classList.remove('hidden');
        } else if (effectiveMode === 'dark') {
            moon.classList.remove('hidden');
        } else {
            sun.classList.remove('hidden');
        }
    }

    function updateActiveModeUI(mode) {
        document.querySelectorAll('.theme-mode-btn').forEach(btn => {
            const isActive = btn.dataset.mode === mode;
            const activeBorder = getComputedStyle(document.documentElement).getPropertyValue('--color-accent').trim() || '#3b82f6';
            const inactiveBg = getComputedStyle(document.documentElement).getPropertyValue('--color-card').trim() || '#ffffff';
            const inactiveBorder = getComputedStyle(document.documentElement).getPropertyValue('--color-card-border').trim() || '#e5e7eb';
            btn.style.borderColor = isActive ? activeBorder : inactiveBorder;
            btn.style.backgroundColor = isActive ? hexToRgba(activeBorder, 0.08) : 'transparent';
        });
    }

    function updateActiveAccentUI(accent) {
        document.querySelectorAll('.accent-btn').forEach(btn => {
            const isActive = btn.dataset.accent === accent;
            btn.style.borderColor = isActive ? ACCENT_COLORS[accent]?.base || '#3b82f6' : 'transparent';
            btn.style.boxShadow = isActive ? `0 0 0 2px var(--color-card), 0 0 0 4px ${ACCENT_COLORS[accent]?.base || '#3b82f6'}` : 'none';
        });
    }

    function updateWorkshopUI(settings) {
        const bgInput = document.getElementById('ws-color-bg');
        const bgText = document.getElementById('ws-color-bg-text');
        const cardInput = document.getElementById('ws-color-card');
        const cardText = document.getElementById('ws-color-card-text');
        const radiusInput = document.getElementById('ws-radius');
        const radiusValue = document.getElementById('ws-radius-value');
        const fontInput = document.getElementById('ws-font-scale');
        const fontValue = document.getElementById('ws-font-scale-value');

        if (bgInput && bgText) {
            const effectiveMode = resolveEffectiveMode(settings);
            const bg = settings.custom?.['--color-bg'] || MODE_PRESETS[effectiveMode]['--color-bg'];
            bgInput.value = bg.startsWith('#') ? bg : '#f9fafb';
            bgText.value = bg;
        }
        if (cardInput && cardText) {
            const effectiveMode = resolveEffectiveMode(settings);
            const card = settings.custom?.['--color-card'] || MODE_PRESETS[effectiveMode]['--color-card'];
            cardInput.value = card.startsWith('#') ? card : '#ffffff';
            cardText.value = card;
        }
        if (radiusInput && radiusValue) {
            const r = settings.custom?.['--radius-base'] || '8px';
            const num = parseInt(r) || 8;
            radiusInput.value = num;
            radiusValue.textContent = num + 'px';
        }
        if (fontInput && fontValue) {
            const s = parseFloat(settings.custom?.['--font-scale'] || '1');
            fontInput.value = Math.round(s * 100);
            fontValue.textContent = Math.round(s * 100) + '%';
        }
    }

    function applyGlobalClassOverrides(effectiveMode) {
        let styleEl = document.getElementById('global-theme-class-overrides');
        if (!styleEl) {
            styleEl = document.createElement('style');
            styleEl.id = 'global-theme-class-overrides';
            document.head.appendChild(styleEl);
        }
        if (effectiveMode === 'dark') {
            styleEl.textContent = `
                .bg-white { background-color: var(--color-card) !important; }
                .bg-gray-50 { background-color: var(--color-card) !important; }
                .bg-gray-100 { background-color: var(--color-card-border) !important; }
                .bg-gray-200 { background-color: var(--color-card-border) !important; }
                .bg-blue-50 { background-color: rgba(59, 130, 246, 0.15) !important; }
                .bg-green-50 { background-color: rgba(16, 185, 129, 0.15) !important; }
                .bg-purple-50 { background-color: rgba(139, 92, 246, 0.15) !important; }
                .bg-amber-50 { background-color: rgba(245, 158, 11, 0.15) !important; }
                .bg-indigo-50 { background-color: rgba(99, 102, 241, 0.15) !important; }
                .bg-gradient-to-r.from-amber-50.to-yellow-50 { background-image: linear-gradient(to right, rgba(245,158,11,0.2), rgba(234,179,8,0.2)) !important; }
                .bg-gradient-to-r.from-indigo-50.to-purple-50 { background-image: linear-gradient(to right, rgba(99,102,241,0.2), rgba(139,92,246,0.2)) !important; }
                .bg-gradient-to-br.from-yellow-100.to-amber-100 { background-image: linear-gradient(to bottom right, rgba(250,204,21,0.2), rgba(251,191,36,0.2)) !important; }
                .bg-gradient-to-br.from-blue-100.to-indigo-100 { background-image: linear-gradient(to bottom right, rgba(147,197,253,0.2), rgba(165,180,252,0.2)) !important; }
                .text-gray-900 { color: var(--color-text) !important; }
                .text-gray-800 { color: var(--color-text) !important; }
                .text-gray-700 { color: var(--color-text) !important; }
                .text-gray-600 { color: var(--color-text-secondary) !important; }
                .text-gray-500 { color: var(--color-text-secondary) !important; }
                .text-gray-400 { color: var(--color-text-muted) !important; }
                .text-gray-300 { color: var(--color-text-muted) !important; }
                .text-blue-600 { color: var(--color-accent) !important; }
                .text-green-600 { color: var(--color-success) !important; }
                .text-purple-600 { color: #a78bfa !important; }
                .text-blue-700 { color: var(--color-accent-hover) !important; }
                .text-amber-700 { color: #fbbf24 !important; }
                .text-indigo-600 { color: #a5b4fc !important; }
                .text-indigo-800 { color: #c7d2fe !important; }
                .border-gray-100 { border-color: var(--color-card-border) !important; }
                .border-gray-200 { border-color: var(--color-card-border) !important; }
                .border-gray-300 { border-color: var(--color-card-border) !important; }
                .border-blue-200 { border-color: rgba(59,130,246,0.4) !important; }
                .border-green-200 { border-color: rgba(16,185,129,0.4) !important; }
                .border-purple-200 { border-color: rgba(139,92,246,0.4) !important; }
                .border-indigo-100 { border-color: rgba(99,102,241,0.3) !important; }
                .border-indigo-200 { border-color: rgba(99,102,241,0.4) !important; }
                .border-amber-200 { border-color: rgba(245,158,11,0.4) !important; }
                .border-amber-100 { border-color: rgba(245,158,11,0.3) !important; }
                .divide-gray-100 > :not([hidden]) ~ :not([hidden]) { border-color: var(--color-card-border) !important; }
                .divide-gray-200 > :not([hidden]) ~ :not([hidden]) { border-color: var(--color-card-border) !important; }
                .shadow-sm { box-shadow: 0 1px 2px 0 rgba(0, 0, 0, 0.3) !important; }
                .shadow { box-shadow: 0 1px 3px 0 rgba(0, 0, 0, 0.4), 0 1px 2px -1px rgba(0, 0, 0, 0.3) !important; }
                .shadow-md { box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.4), 0 2px 4px -2px rgba(0, 0, 0, 0.3) !important; }
                .shadow-lg { box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.5), 0 4px 6px -4px rgba(0, 0, 0, 0.4) !important; }
                .shadow-xl { box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.5), 0 8px 10px -6px rgba(0, 0, 0, 0.4) !important; }
                .shadow-2xl { box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.6) !important; }
                .ring-gray-100 { --tw-ring-color: var(--color-card-border) !important; }
                .ring-gray-200 { --tw-ring-color: var(--color-card-border) !important; }
                .hover\:bg-gray-50:hover { background-color: var(--color-card-border) !important; }
                .hover\:bg-gray-100:hover { background-color: rgba(255,255,255,0.06) !important; }
                .hover\:bg-gray-50\/50:hover { background-color: rgba(255,255,255,0.04) !important; }
                .hover\:text-gray-800:hover { color: var(--color-text) !important; }
                .hover\:text-gray-900:hover { color: var(--color-text) !important; }
                .placeholder\:text-gray-400::placeholder { color: var(--color-text-muted) !important; }
                .bg-white\/80 { background-color: rgba(31, 41, 55, 0.8) !important; }
                .bg-white\/60 { background-color: rgba(31, 41, 55, 0.6) !important; }
                .bg-black\/40 { background-color: rgba(0, 0, 0, 0.6) !important; }
                .backdrop-blur-md { --tw-backdrop-blur: blur(12px); }
                input[type="color"] { background-color: var(--color-card) !important; }
                select, input, textarea {
                    background-color: var(--color-card) !important;
                    color: var(--color-text) !important;
                    border-color: var(--color-card-border) !important;
                }
                select:focus, input:focus, textarea:focus {
                    border-color: var(--color-accent) !important;
                    box-shadow: 0 0 0 1px var(--color-accent) !important;
                }
                table { color: var(--color-text) !important; }
                th { color: var(--color-text-secondary) !important; }
                tr:nth-child(even) td { background-color: rgba(255,255,255,0.02); }
            `;
        } else {
            styleEl.textContent = '';
        }
    }

    function applyViewerOverrides(effectiveMode) {
        const existingStyle = document.getElementById('viewer-theme-overrides');
        if (!existingStyle) {
            const style = document.createElement('style');
            style.id = 'viewer-theme-overrides';
            document.head.appendChild(style);
        }
        const styleEl = document.getElementById('viewer-theme-overrides');
        if (effectiveMode === 'dark') {
            styleEl.textContent = `
                .viewer-container { background-color: var(--color-overlay) !important; }
                .viewer-toolbar { background-color: var(--color-toolbar-bg) !important; }
                .viewer-button, .viewer-toolbar li { color: var(--color-toolbar-text) !important; }
                .viewer-button:hover { background-color: rgba(255,255,255,0.1) !important; }
                .viewer-title { color: var(--color-toolbar-text) !important; }
                .viewer-navbar { background-color: var(--color-toolbar-bg) !important; }
                .viewer-list { background-color: transparent !important; }
            `;
        } else {
            styleEl.textContent = `
                .viewer-container { background-color: var(--color-overlay) !important; }
                .viewer-toolbar { background-color: var(--color-toolbar-bg) !important; }
                .viewer-button, .viewer-toolbar li { color: var(--color-toolbar-text) !important; }
                .viewer-button:hover { background-color: rgba(255,255,255,0.1) !important; }
                .viewer-title { color: var(--color-toolbar-text) !important; }
                .viewer-navbar { background-color: var(--color-toolbar-bg) !important; }
            `;
        }
    }

    function openPanel() {
        const panel = document.getElementById('theme-panel');
        const overlay = document.getElementById('theme-panel-overlay');
        if (panel) {
            panel.classList.remove('translate-x-full');
        }
        if (overlay) {
            overlay.classList.remove('hidden');
            requestAnimationFrame(() => overlay.classList.remove('opacity-0'));
        }
    }

    function closePanel() {
        const panel = document.getElementById('theme-panel');
        const overlay = document.getElementById('theme-panel-overlay');
        if (panel) {
            panel.classList.add('translate-x-full');
        }
        if (overlay) {
            overlay.classList.add('opacity-0');
            setTimeout(() => overlay.classList.add('hidden'), 300);
        }
    }

    function renderPresetList(settings) {
        const container = document.getElementById('preset-list');
        if (!container) return;
        const presets = loadPresets();
        const keys = Object.keys(presets);
        if (keys.length === 0) {
            container.innerHTML = `<p class="text-xs" style="color: var(--color-text-muted);">暂无自定义 Preset。调整参数后点击上方保存。</p>`;
            return;
        }
        const accent = getComputedStyle(document.documentElement).getPropertyValue('--color-accent').trim() || '#3b82f6';
        container.innerHTML = keys.map(key => {
            const p = presets[key];
            const isActive = settings.activePreset === key;
            return `
                <div class="flex items-center gap-2 p-2 rounded-lg transition" data-preset="${key}" style="background-color: ${isActive ? hexToRgba(accent, 0.08) : 'transparent'}; border: 1px solid ${isActive ? accent : 'var(--color-card-border)'};">
                    <div class="flex items-center gap-1.5 flex-1 min-w-0">
                        <span class="w-3 h-3 rounded-full" style="background-color: ${p['--color-bg'] || '#f9fafb'}; border: 1px solid var(--color-card-border);"></span>
                        <span class="w-3 h-3 rounded-full" style="background-color: ${p['--color-card'] || '#ffffff'}; border: 1px solid var(--color-card-border);"></span>
                        <span class="text-xs font-medium truncate" style="color: var(--color-text);">${key}</span>
                    </div>
                    <button class="preset-apply-btn p-1 rounded transition hover:opacity-70" data-preset="${key}" title="应用">
                        <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24" style="color: var(--color-accent);"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"></path></svg>
                    </button>
                    <button class="preset-delete-btn p-1 rounded transition hover:opacity-70" data-preset="${key}" title="删除">
                        <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24" style="color: var(--color-danger);"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"></path></svg>
                    </button>
                </div>
            `;
        }).join('');

        container.querySelectorAll('.preset-apply-btn').forEach(btn => {
            btn.addEventListener('click', (e) => {
                e.stopPropagation();
                applyPreset(btn.dataset.preset);
            });
        });
        container.querySelectorAll('.preset-delete-btn').forEach(btn => {
            btn.addEventListener('click', (e) => {
                e.stopPropagation();
                deletePreset(btn.dataset.preset);
            });
        });
    }

    function applyPreset(name) {
        const presets = loadPresets();
        const preset = presets[name];
        if (!preset) return;
        const settings = loadSettings();
        settings.custom = Object.assign({}, settings.custom, {
            '--color-bg': preset['--color-bg'] || null,
            '--color-card': preset['--color-card'] || null,
            '--radius-base': preset['--radius-base'] || '8px',
            '--font-scale': preset['--font-scale'] || '1',
        });
        if (preset.accent) settings.accent = preset.accent;
        if (preset.mode) settings.mode = preset.mode;
        settings.activePreset = name;
        saveSettings(settings);
        applyTheme(settings);
        renderPresetList(settings);
    }

    function deletePreset(name) {
        const presets = loadPresets();
        delete presets[name];
        savePresets(presets);
        const settings = loadSettings();
        if (settings.activePreset === name) settings.activePreset = null;
        saveSettings(settings);
        renderPresetList(settings);
    }

    function savePresetFromCurrent() {
        const settings = loadSettings();
        const name = prompt('为这个 Preset 命名：');
        if (!name || !name.trim()) return;
        const presets = loadPresets();
        const effectiveMode = resolveEffectiveMode(settings);
        presets[name.trim()] = {
            '--color-bg': settings.custom?.['--color-bg'] || MODE_PRESETS[effectiveMode]['--color-bg'],
            '--color-card': settings.custom?.['--color-card'] || MODE_PRESETS[effectiveMode]['--color-card'],
            '--radius-base': settings.custom?.['--radius-base'] || '8px',
            '--font-scale': settings.custom?.['--font-scale'] || '1',
            accent: settings.accent,
            mode: settings.mode,
        };
        savePresets(presets);
        settings.activePreset = name.trim();
        saveSettings(settings);
        renderPresetList(settings);
    }

    function resetToDefault() {
        localStorage.removeItem(STORAGE_KEY);
        const settings = JSON.parse(JSON.stringify(DEFAULT_SETTINGS));
        saveSettings(settings);
        applyTheme(settings);
        renderPresetList(settings);
    }

    function init() {
        let settings = loadSettings();
        applyTheme(settings);

        const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)');
        mediaQuery.addEventListener('change', () => {
            if (settings.mode === 'system') {
                applyTheme(settings);
            }
        });

        document.addEventListener('DOMContentLoaded', () => {
            const toggleBtn = document.getElementById('theme-toggle-btn');
            if (toggleBtn) {
                toggleBtn.addEventListener('click', openPanel);
            }
            const closeBtn = document.getElementById('theme-panel-close');
            if (closeBtn) closeBtn.addEventListener('click', closePanel);
            const overlay = document.getElementById('theme-panel-overlay');
            if (overlay) overlay.addEventListener('click', closePanel);

            document.querySelectorAll('.theme-mode-btn').forEach(btn => {
                btn.addEventListener('click', () => {
                    settings = loadSettings();
                    settings.mode = btn.dataset.mode;
                    settings.activePreset = null;
                    saveSettings(settings);
                    applyTheme(settings);
                    updateWorkshopUI(settings);
                });
            });

            document.querySelectorAll('.accent-btn').forEach(btn => {
                btn.addEventListener('click', () => {
                    settings = loadSettings();
                    settings.accent = btn.dataset.accent;
                    saveSettings(settings);
                    applyTheme(settings);
                });
            });

            const resetBtn = document.getElementById('reset-default-btn');
            if (resetBtn) resetBtn.addEventListener('click', resetToDefault);

            const wsBg = document.getElementById('ws-color-bg');
            const wsBgText = document.getElementById('ws-color-bg-text');
            if (wsBg && wsBgText) {
                const sync = (val) => {
                    if (!/^#[0-9a-fA-F]{6}$/.test(val)) return;
                    settings = loadSettings();
                    settings.custom = settings.custom || {};
                    settings.custom['--color-bg'] = val;
                    settings.activePreset = null;
                    saveSettings(settings);
                    applyTheme(settings);
                    wsBg.value = val;
                    wsBgText.value = val;
                };
                wsBg.addEventListener('input', (e) => sync(e.target.value));
                wsBgText.addEventListener('change', (e) => sync(e.target.value.trim()));
            }

            const wsCard = document.getElementById('ws-color-card');
            const wsCardText = document.getElementById('ws-color-card-text');
            if (wsCard && wsCardText) {
                const sync = (val) => {
                    if (!/^#[0-9a-fA-F]{6}$/.test(val)) return;
                    settings = loadSettings();
                    settings.custom = settings.custom || {};
                    settings.custom['--color-card'] = val;
                    settings.activePreset = null;
                    saveSettings(settings);
                    applyTheme(settings);
                    wsCard.value = val;
                    wsCardText.value = val;
                };
                wsCard.addEventListener('input', (e) => sync(e.target.value));
                wsCardText.addEventListener('change', (e) => sync(e.target.value.trim()));
            }

            const wsRadius = document.getElementById('ws-radius');
            const wsRadiusValue = document.getElementById('ws-radius-value');
            if (wsRadius && wsRadiusValue) {
                wsRadius.addEventListener('input', (e) => {
                    const val = parseInt(e.target.value) || 0;
                    wsRadiusValue.textContent = val + 'px';
                    settings = loadSettings();
                    settings.custom = settings.custom || {};
                    settings.custom['--radius-base'] = val + 'px';
                    settings.activePreset = null;
                    saveSettings(settings);
                    applyTheme(settings);
                });
            }

            const wsFont = document.getElementById('ws-font-scale');
            const wsFontValue = document.getElementById('ws-font-scale-value');
            if (wsFont && wsFontValue) {
                wsFont.addEventListener('input', (e) => {
                    const val = parseInt(e.target.value) || 100;
                    wsFontValue.textContent = val + '%';
                    settings = loadSettings();
                    settings.custom = settings.custom || {};
                    settings.custom['--font-scale'] = (val / 100).toString();
                    settings.activePreset = null;
                    saveSettings(settings);
                    applyTheme(settings);
                });
            }

            const wsSavePreset = document.getElementById('ws-save-preset');
            if (wsSavePreset) wsSavePreset.addEventListener('click', savePresetFromCurrent);

            const wsResetCustom = document.getElementById('ws-reset-custom');
            if (wsResetCustom) {
                wsResetCustom.addEventListener('click', () => {
                    settings = loadSettings();
                    settings.custom = {
                        '--color-bg': null,
                        '--color-card': null,
                        '--radius-base': '8px',
                        '--font-scale': '1',
                    };
                    settings.activePreset = null;
                    saveSettings(settings);
                    applyTheme(settings);
                    updateWorkshopUI(settings);
                });
            }

            renderPresetList(settings);
        });
    }

    init();
})();
