class OnThisDayRenderer {
    constructor(options) {
        this.container = options.container;
        this.items = options.initialData || [];
        this._flatPhotos = [];
        this._photoIndexMap = new Map();
        this._rebuildIndex();
        this.render();
    }

    async loadData(mode = 'upload') {
        try {
            const resp = await fetch(`/api/timeline/on-this-day?mode=${mode}`);
            const data = await resp.json();
            this.items = data.items || [];
            this.render();
        } catch (e) {
            console.error('Failed to load on-this-day data:', e);
        }
    }

    _rebuildIndex() {
        this._flatPhotos = [];
        this._photoIndexMap.clear();
        let globalIdx = 0;
        this.items.forEach(yearData => {
            (yearData.photos || []).forEach(photo => {
                this._flatPhotos.push({ src: photo.url, alt: photo.original_filename, url: photo.url });
                this._photoIndexMap.set(String(yearData.year) + ':' + String(photo.photo_id), globalIdx);
                globalIdx++;
            });
        });
    }

    render() {
        if (!this.container) return;
        this._rebuildIndex();

        if (!this.items || this.items.length === 0) {
            this.container.innerHTML = `
                <div class="w-full py-12 text-center bg-gradient-to-br from-amber-50 to-orange-50 rounded-xl border border-amber-100">
                    <svg class="w-12 h-12 mx-auto mb-3 text-amber-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z"></path></svg>
                    <p class="text-gray-500">往年的今天还没有照片</p>
                </div>
            `;
            return;
        }

        let html = '';
        this.items.forEach(yearData => {
            let stackHtml = '';
            const photos = yearData.photos || [];
            photos.forEach((photo, idx) => {
                const translateY = idx * 4;
                const scale = 1 - idx * 0.04;
                const zIndex = 10 - idx;
                const isTop = idx === 0;
                stackHtml += `
                    <div class="absolute inset-0 transition-all duration-300 on-this-day-layer ${isTop ? 'group-hover:-translate-y-1' : ''}" 
                         style="transform: translateY(${translateY}px) scale(${scale}); z-index: ${zIndex};">
                        <img src="${photo.url}" alt="${this._escapeHtml(photo.original_filename)}"
                             class="w-full h-full object-cover rounded-xl ${isTop ? 'cursor-zoom-in' : 'pointer-events-none'}"
                             data-year="${yearData.year}" data-photo-id="${photo.photo_id}">
                    </div>
                `;
            });

            const firstPhoto = photos[0];
            html += `
                <div class="on-this-day-card shrink-0 w-48 relative group cursor-pointer on-this-day-clickable"
                     data-year="${yearData.year}" data-photo-id="${firstPhoto ? firstPhoto.photo_id : ''}">
                    <div class="text-center mb-2">
                        <span class="inline-block bg-gradient-to-r from-amber-400 to-orange-500 text-white text-sm font-bold px-3 py-1 rounded-full shadow">
                            ${yearData.year}年
                        </span>
                    </div>
                    <div class="relative h-64 rounded-xl overflow-hidden shadow-lg">
                        ${stackHtml}
                        ${photos.length > 1 ? `
                        <div class="absolute bottom-2 right-2 bg-black/60 text-white text-[10px] px-2 py-0.5 rounded-full backdrop-blur-sm pointer-events-none z-20">
                            ${photos.length} 张
                        </div>` : ''}
                    </div>
                    <p class="text-center text-xs text-gray-500 mt-2">${photos.length} 张照片</p>
                </div>
            `;
        });

        this.container.innerHTML = html;
        this._bindListeners();
    }

    _bindListeners() {
        if (!this.container) return;
        this.container.querySelectorAll('.on-this-day-clickable').forEach(card => {
            if (card.dataset.listenerBound === '1') return;
            card.dataset.listenerBound = '1';
            card.addEventListener('click', (e) => this._onCardClick(e, card));
        });
    }

    _onCardClick(e, card) {
        if (this._flatPhotos.length === 0) return;
        const year = card.dataset.year;
        const photoId = card.dataset.photoId;
        let startIdx = 0;
        const key = String(year) + ':' + String(photoId);
        if (this._photoIndexMap.has(key)) {
            startIdx = this._photoIndexMap.get(key);
        } else {
            for (let i = 0; i < this.items.length; i++) {
                if (String(this.items[i].year) === String(year)) {
                    const base = this._photoIndexMap.get(String(year) + ':' + String((this.items[i].photos || [{}])[0].photo_id));
                    if (base !== undefined) { startIdx = base; break; }
                }
            }
        }
        const viewer = new Viewer(document.body, {
            images: this._flatPhotos,
            toolbar: true,
            navbar: true,
            title: false,
            url: 'src'
        });
        viewer.view(startIdx);
    }

    _escapeHtml(str) {
        const div = document.createElement('div');
        div.textContent = str || '';
        return div.innerHTML;
    }
}
