class TimelineRenderer {
    constructor(options) {
        this.container = options.container;
        this.yearAnchors = options.yearAnchors;
        this.totalCountEl = options.totalCountEl;
        this.data = options.initialData || { groups: {}, sorted_keys: [], years: [], albums: [], total_photos: 0 };
        this.virtualScrollers = new Map();
        this._allPhotos = [];
        this._photoIndexMap = new Map();
        this._rebuildPhotoIndex();
        this.render();
    }

    async loadData(mode = 'upload', albumIds = null) {
        try {
            const params = new URLSearchParams();
            params.set('mode', mode);
            if (albumIds && albumIds.length > 0) {
                params.set('albums', albumIds.join(','));
            }
            const resp = await fetch(`/api/timeline/photos?${params.toString()}`);
            this.data = await resp.json();
            this._rebuildPhotoIndex();
            this.render();
        } catch (e) {
            console.error('Failed to load timeline data:', e);
        }
    }

    _rebuildPhotoIndex() {
        this._allPhotos = [];
        this._photoIndexMap.clear();
        const groups = this.data.groups || {};
        const sortedKeys = this.data.sorted_keys || [];
        sortedKeys.forEach(key => {
            const group = groups[key];
            if (!group) return;
            (group.photos || []).forEach(photo => {
                this._allPhotos.push({
                    src: photo.url,
                    alt: photo.original_filename,
                    url: photo.url
                });
                this._photoIndexMap.set(photo.photo_id, this._allPhotos.length - 1);
            });
        });
    }

    render() {
        this._destroyScrollers();
        this._renderYearAnchors();
        this._renderTotalCount();

        if (!this.container) return;

        if (!this.data.total_photos || this.data.total_photos === 0) {
            this.container.innerHTML = this._renderEmpty();
            return;
        }

        let html = '';
        const groups = this.data.groups || {};
        const sortedKeys = this.data.sorted_keys || [];
        let lastYear = null;

        sortedKeys.forEach((key) => {
            const group = groups[key];
            if (!group) return;
            const year = group.year;

            if (year && year !== lastYear) {
                lastYear = year;
                html += `
                    <div id="year-${year}" class="year-marker -ml-4 mb-4 pl-4 border-l-4 border-primary">
                        <h2 class="text-2xl font-bold text-gray-800">${year}年</h2>
                    </div>
                `;
            }

            html += `
                <section class="timeline-group" data-date-key="${this._escapeAttr(key)}" data-year="${year || ''}">
                    <div class="flex items-center justify-between mb-3">
                        <h3 class="text-lg font-semibold text-gray-800 flex items-center">
                            <svg class="w-5 h-5 mr-2 text-primary" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z"></path></svg>
                            ${this._escapeHtml(group.label)}
                        </h3>
                        <span class="text-sm text-gray-400">${(group.photos || []).length} 张</span>
                    </div>
                    <div class="timeline-photo-scroll relative overflow-x-auto pb-3 scrollbar-thin" data-date-key="${this._escapeAttr(key)}" data-photo-count="${(group.photos || []).length}">
                        <div class="timeline-photo-row flex gap-3 min-w-max">
                        </div>
                    </div>
                </section>
            `;
        });

        this.container.innerHTML = html;
        this._initScrollers();
        this._bindYearAnchors();
    }

    _renderYearAnchors() {
        if (!this.yearAnchors) return;
        const years = this.data.years || [];
        this.yearAnchors.innerHTML = years.map(y => `
            <a href="#year-${y}" class="year-anchor-btn px-3 py-1 rounded-full text-sm font-medium bg-gray-100 text-gray-700 hover:bg-primary hover:text-white transition whitespace-nowrap" data-year="${y}">
                ${y}年
            </a>
        `).join('');
    }

    _bindYearAnchors() {
        if (!this.yearAnchors) return;
        this.yearAnchors.querySelectorAll('.year-anchor-btn').forEach(btn => {
            if (btn.dataset.listenerBound === '1') return;
            btn.dataset.listenerBound = '1';
            btn.addEventListener('click', (e) => {
                e.preventDefault();
                const year = btn.dataset.year;
                const target = document.getElementById('year-' + year);
                if (target) {
                    const offset = 120;
                    const top = target.getBoundingClientRect().top + window.pageYOffset - offset;
                    window.scrollTo({ top, behavior: 'smooth' });
                }
            });
        });
    }

    _renderTotalCount() {
        if (this.totalCountEl) {
            this.totalCountEl.textContent = `共 ${this.data.total_photos || 0} 张`;
        }
    }

    _renderEmpty() {
        return `
            <div class="text-center py-20 bg-white rounded-2xl shadow-sm border border-gray-100">
                <div class="w-24 h-24 mx-auto mb-6 bg-gradient-to-br from-blue-100 to-indigo-100 rounded-full flex items-center justify-center">
                    <svg class="w-12 h-12 text-blue-500" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z"></path></svg>
                </div>
                <h3 class="text-xl font-semibold text-gray-800 mb-2">时间线还没有照片</h3>
                <p class="text-gray-500 mb-6 max-w-md mx-auto">公开相册中还没有照片，上传照片后即可在此浏览时间线</p>
            </div>
        `;
    }

    _initScrollers() {
        if (!this.container) return;
        const groups = this.data.groups || {};
        this.container.querySelectorAll('.timeline-photo-scroll').forEach(scrollEl => {
            const key = scrollEl.dataset.dateKey;
            const group = groups[key];
            if (!group) return;

            const scroller = new VirtualScroller({
                scrollContainer: scrollEl,
                itemRenderer: (photo) => this._renderPhotoItem(photo),
                itemWidth: 160,
                itemGap: 12,
                bufferSize: 5
            });
            scroller.setItems(group.photos || []);
            this.virtualScrollers.set(key, scroller);
        });
    }

    _renderPhotoItem(photo) {
        const div = document.createElement('div');
        div.className = 'photo-thumbnail shrink-0 w-40 h-32 rounded-xl overflow-hidden shadow-sm hover:shadow-xl transition-all duration-300 bg-white group relative';
        div.dataset.photoId = photo.photo_id;
        div.innerHTML = `
            <img src="${photo.url}" alt="${this._escapeHtml(photo.original_filename)}"
                 class="w-full h-full object-cover cursor-zoom-in transition-transform duration-500 hover:scale-105 timeline-img"
                 data-url="${photo.url}" data-photo-id="${photo.photo_id}">
            <div class="absolute inset-x-0 bottom-0 bg-gradient-to-t from-black/70 via-black/20 to-transparent p-2 opacity-0 group-hover:opacity-100 transition-all duration-200">
                <p class="text-white text-xs truncate">${this._escapeHtml(photo.original_filename)}</p>
                <p class="text-gray-300 text-[10px] mt-0.5 truncate">${this._escapeHtml(photo.album_title || '')}</p>
            </div>
        `;

        const img = div.querySelector('img');
        if (img) {
            img.addEventListener('click', () => {
                const idx = this._photoIndexMap.get(photo.photo_id) || 0;
                const viewer = new Viewer(document.body, {
                    images: this._allPhotos,
                    toolbar: true,
                    navbar: true,
                    title: false,
                    url: 'src'
                });
                viewer.view(idx);
            });
        }
        return div;
    }

    _destroyScrollers() {
        this.virtualScrollers.forEach(s => s.destroy());
        this.virtualScrollers.clear();
    }

    _escapeHtml(str) {
        const div = document.createElement('div');
        div.textContent = str || '';
        return div.innerHTML;
    }

    _escapeAttr(str) {
        return (str || '').replace(/"/g, '&quot;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    }
}
