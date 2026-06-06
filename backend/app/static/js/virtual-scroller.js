class VirtualScroller {
    constructor(options) {
        this.scrollContainer = options.scrollContainer;
        this.itemRenderer = options.itemRenderer;
        this.items = [];
        this.itemWidth = options.itemWidth || 176;
        this.itemGap = options.itemGap || 12;
        this.bufferSize = options.bufferSize || 5;
        this.rowInner = null;
        this.placeholderLeft = null;
        this.placeholderRight = null;
        this.visibleStart = 0;
        this.visibleEnd = 0;
        this._rafId = null;

        if (this.scrollContainer) {
            this.init();
        }
    }

    init() {
        this.rowInner = this.scrollContainer.querySelector('.timeline-photo-row');
        if (!this.rowInner) return;

        this.rowInner.style.position = 'relative';
        this.placeholderLeft = document.createElement('div');
        this.placeholderRight = document.createElement('div');
        this.placeholderLeft.style.flexShrink = '0';
        this.placeholderRight.style.flexShrink = '0';
        this.rowInner.prepend(this.placeholderLeft);
        this.rowInner.appendChild(this.placeholderRight);

        this.scrollContainer.addEventListener('scroll', () => this.onScroll(), { passive: true });
        window.addEventListener('resize', () => this.updateVisibleRange());
    }

    setItems(items) {
        this.items = items || [];
        this.renderAll();
        this.updateVisibleRange();
    }

    onScroll() {
        if (this._rafId) return;
        this._rafId = requestAnimationFrame(() => {
            this._rafId = null;
            this.updateVisibleRange();
        });
    }

    updateVisibleRange() {
        if (!this.scrollContainer || this.items.length === 0) return;
        const viewportLeft = this.scrollContainer.scrollLeft;
        const viewportRight = viewportLeft + this.scrollContainer.clientWidth;
        const itemTotalWidth = this.itemWidth + this.itemGap;

        const startIdx = Math.max(0, Math.floor(viewportLeft / itemTotalWidth) - this.bufferSize);
        const endIdx = Math.min(this.items.length, Math.ceil(viewportRight / itemTotalWidth) + this.bufferSize);

        if (startIdx !== this.visibleStart || endIdx !== this.visibleEnd) {
            this.visibleStart = startIdx;
            this.visibleEnd = endIdx;
            this.renderVisible();
        }
    }

    renderAll() {
        if (!this.rowInner) return;
        const totalWidth = this.items.length * (this.itemWidth + this.itemGap);
        this.placeholderLeft.style.width = '0px';
        this.placeholderRight.style.width = '0px';

        const existingItems = this.rowInner.querySelectorAll('.photo-thumbnail');
        existingItems.forEach(el => el.remove());
        this.visibleStart = 0;
        this.visibleEnd = 0;
    }

    renderVisible() {
        if (!this.rowInner) return;
        const itemTotalWidth = this.itemWidth + this.itemGap;

        this.placeholderLeft.style.width = (this.visibleStart * itemTotalWidth) + 'px';

        const existingItems = this.rowInner.querySelectorAll('.photo-thumbnail');
        const existingMap = new Map();
        existingItems.forEach(el => existingMap.set(parseInt(el.dataset.photoId), el));

        const fragment = document.createDocumentFragment();
        for (let i = this.visibleStart; i < this.visibleEnd; i++) {
            const photo = this.items[i];
            if (!photo) continue;
            if (!existingMap.has(photo.photo_id)) {
                fragment.appendChild(this.itemRenderer(photo));
            } else {
                existingMap.delete(photo.photo_id);
            }
        }

        existingMap.forEach(el => el.remove());

        if (this.placeholderLeft.nextSibling !== this.rowInner.firstChild) {
            this.rowInner.insertBefore(fragment, this.placeholderLeft.nextSibling);
        } else {
            this.rowInner.insertBefore(fragment, this.placeholderRight);
        }

        const rightItems = this.items.length - this.visibleEnd;
        this.placeholderRight.style.width = Math.max(0, rightItems * itemTotalWidth) + 'px';
    }

    destroy() {
        if (this._rafId) cancelAnimationFrame(this._rafId);
    }
}
