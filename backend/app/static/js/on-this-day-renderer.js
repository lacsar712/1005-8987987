class OnThisDayRenderer {
    constructor(options) {
        this.container = options.container;
        this.items = options.initialData || [];
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

    render() {
        if (!this.container) return;

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
            (yearData.photos || []).forEach((photo, idx) => {
                const translateY = idx * 4;
                const scale = 1 - idx * 0.04;
                const zIndex = 10 - idx;
                stackHtml += `
                    <div class="absolute inset-0 transition-all duration-300" style="transform: translateY(${translateY}px) scale(${scale}); z-index: ${zIndex};">
                        <img src="${photo.url}" alt="${this._escapeHtml(photo.original_filename)}"
                             class="w-full h-full object-cover rounded-xl cursor-zoom-in on-this-day-img"
                             data-url="${photo.url}">
                    </div>
                `;
            });

            html += `
                <div class="on-this-day-card shrink-0 w-48 relative group">
                    <div class="text-center mb-2">
                        <span class="inline-block bg-gradient-to-r from-amber-400 to-orange-500 text-white text-sm font-bold px-3 py-1 rounded-full shadow">
                            ${yearData.year}年
                        </span>
                    </div>
                    <div class="relative h-64 rounded-xl overflow-hidden shadow-lg">
                        ${stackHtml}
                    </div>
                    <p class="text-center text-xs text-gray-500 mt-2">${(yearData.photos || []).length} 张照片</p>
                </div>
            `;
        });

        this.container.innerHTML = html;
    }

    _escapeHtml(str) {
        const div = document.createElement('div');
        div.textContent = str || '';
        return div.innerHTML;
    }
}
