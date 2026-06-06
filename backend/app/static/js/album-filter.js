class AlbumFilter {
    constructor(options) {
        this.container = options.container;
        this.albums = options.initialAlbums || [];
        this.onChange = options.onChange || (() => {});
        this.selectedIds = new Set(['all']);
        this._isUpdating = false;
        this.init();
    }

    init() {
        if (!this.container) return;
        this.container.addEventListener('change', (e) => {
            if (e.target.classList.contains('album-checkbox')) {
                this.onCheckboxChange(e.target);
            }
        });
    }

    onCheckboxChange(checkbox) {
        if (this._isUpdating) return;
        const albumId = checkbox.dataset.albumId;
        const checked = checkbox.checked;

        if (albumId === 'all') {
            this._isUpdating = true;
            this.selectedIds.clear();
            if (checked) {
                this.selectedIds.add('all');
                this.container.querySelectorAll('.album-checkbox').forEach(cb => {
                    cb.checked = cb.dataset.albumId === 'all';
                });
            }
            this._isUpdating = false;
        } else {
            this._isUpdating = true;
            const id = parseInt(albumId);
            if (checked) {
                this.selectedIds.add(id);
                this.selectedIds.delete('all');
                const allCb = this.container.querySelector('.album-checkbox[data-album-id="all"]');
                if (allCb) allCb.checked = false;
            } else {
                this.selectedIds.delete(id);
                if (this.selectedIds.size === 0) {
                    this.selectedIds.add('all');
                    const allCb = this.container.querySelector('.album-checkbox[data-album-id="all"]');
                    if (allCb) allCb.checked = true;
                }
            }
            this._isUpdating = false;
        }
        this.onChange(this.getSelectedIds());
    }

    getSelectedIds() {
        if (this.selectedIds.has('all')) {
            return null;
        }
        return Array.from(this.selectedIds);
    }

    updateAlbums(albums) {
        this.albums = albums || [];
        if (!this.container) return;

        const totalCount = this.albums.reduce((sum, a) => sum + (a.photo_count || 0), 0);
        let html = `
            <label class="flex items-center p-2 rounded-lg hover:bg-gray-50 cursor-pointer transition album-filter-item" data-album-id="all">
                <input type="checkbox" class="album-checkbox w-4 h-4 text-primary rounded mr-3" data-album-id="all" ${this.selectedIds.has('all') ? 'checked' : ''}>
                <span class="text-sm text-gray-700 flex-1">全部相册</span>
                <span class="text-xs text-gray-400">${totalCount}</span>
            </label>
        `;
        this.albums.forEach(album => {
            const id = album.id;
            const checked = this.selectedIds.has(id) ? 'checked' : '';
            html += `
                <label class="flex items-center p-2 rounded-lg hover:bg-gray-50 cursor-pointer transition album-filter-item" data-album-id="${id}">
                    <input type="checkbox" class="album-checkbox w-4 h-4 text-primary rounded mr-3" data-album-id="${id}" ${checked}>
                    <span class="text-sm text-gray-700 flex-1 truncate">${this._escapeHtml(album.title)}</span>
                    <span class="text-xs text-gray-400">${album.photo_count || 0}</span>
                </label>
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
