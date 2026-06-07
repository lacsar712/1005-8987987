class PhotoEditor {
    constructor() {
        this.canvas = document.getElementById('editorCanvas');
        this.ctx = this.canvas.getContext('2d');
        this.container = document.getElementById('canvasContainer');
        this.originalImg = new Image();
        this.originalImg.crossOrigin = 'anonymous';

        this.workCanvas = document.createElement('canvas');
        this.workCtx = this.workCanvas.getContext('2d');

        this.operations = [...(window.INITIAL_OPERATIONS || [])];
        this.versionsCache = {};
        (window.INITIAL_VERSIONS || []).forEach(v => {
            this.versionsCache[v.id] = v;
        });

        this.currentTool = null;
        this.previewOp = null;
        this.compareMode = false;

        this.mosaicDrawing = false;
        this.mosaicStart = null;
        this.tempMosaicRect = null;
        this._mosaicCellSize = 15;

        this.cropBox = { x: 0, y: 0, width: 0, height: 0, active: false, ratio: null };
        this._cropDrag = null;

        this.previewVersionId = null;
        this.savedOperationsBeforePreview = null;
        this.savedPreviewOpBeforePreview = null;

        this.init();
    }

    init() {
        this.originalImg.onload = () => {
            this.resetCanvasSize();
            this.render();
        };
        this.originalImg.src = window.ORIGINAL_URL;

        this.bindEvents();
        this.updateOperationsList();
    }

    resetCanvasSize() {
        const maxW = this.container.clientWidth - 32;
        const maxH = this.container.clientHeight - 32;
        const naturalW = this.originalImg.naturalWidth;
        const naturalH = this.originalImg.naturalHeight;
        const ratio = Math.min(maxW / naturalW, maxH / naturalH, 1);

        this.canvas.width = naturalW;
        this.canvas.height = naturalH;
        this.canvas.style.width = (naturalW * ratio) + 'px';
        this.canvas.style.height = (naturalH * ratio) + 'px';
        this.workCanvas.width = naturalW;
        this.workCanvas.height = naturalH;
    }

    render() {
        this.workCtx.setTransform(1, 0, 0, 1, 0, 0);
        this.workCtx.clearRect(0, 0, this.workCanvas.width, this.workCanvas.height);
        this.workCtx.drawImage(this.originalImg, 0, 0);

        for (let i = 0; i < this.operations.length; i++) {
            this.applyOperation(this.workCtx, this.operations[i]);
        }

        if (this.previewOp) {
            this.applyOperation(this.workCtx, this.previewOp);
        }

        this.canvas.setTransform(1, 0, 0, 1, 0, 0);
        this.canvas.width = this.workCanvas.width;
        this.canvas.height = this.workCanvas.height;
        this.ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);
        this.ctx.drawImage(this.workCanvas, 0, 0);

        if (this.tempMosaicRect) {
            this.drawTempMosaic(this.ctx, this.tempMosaicRect);
        }

        if (this.cropBox.active && this.currentTool === 'crop') {
            this.drawCropOverlay();
        }

        this.updateUndoState();
    }

    applyOperation(ctx, op) {
        switch (op.type) {
            case 'rotate':
                this.applyRotate(ctx, op.params.angle || 0);
                break;
            case 'crop':
                this.applyCrop(ctx, op.params);
                break;
            case 'brightness':
                this.applyBrightness(ctx, op.params.value || 1);
                break;
            case 'contrast':
                this.applyContrast(ctx, op.params.value || 1);
                break;
            case 'mosaic':
                this.applyMosaic(ctx, op.params);
                break;
        }
    }

    applyRotate(ctx, angle) {
        const rad = -angle * Math.PI / 180;
        const w = ctx.canvas.width;
        const h = ctx.canvas.height;
        const cos = Math.abs(Math.cos(rad));
        const sin = Math.abs(Math.sin(rad));
        const newW = Math.ceil(w * cos + h * sin);
        const newH = Math.ceil(w * sin + h * cos);

        const tmp = document.createElement('canvas');
        tmp.width = newW;
        tmp.height = newH;
        const tctx = tmp.getContext('2d');
        tctx.setTransform(1, 0, 0, 1, 0, 0);
        tctx.translate(newW / 2, newH / 2);
        tctx.rotate(rad);
        tctx.drawImage(ctx.canvas, -w / 2, -h / 2);

        ctx.canvas.width = newW;
        ctx.canvas.height = newH;
        ctx.setTransform(1, 0, 0, 1, 0, 0);
        ctx.clearRect(0, 0, newW, newH);
        ctx.drawImage(tmp, 0, 0);
    }

    applyCrop(ctx, params) {
        const x = Math.max(0, Math.min(params.x || 0, ctx.canvas.width));
        const y = Math.max(0, Math.min(params.y || 0, ctx.canvas.height));
        const w = Math.max(1, Math.min(params.width || ctx.canvas.width, ctx.canvas.width - x));
        const h = Math.max(1, Math.min(params.height || ctx.canvas.height, ctx.canvas.height - y));

        const tmp = document.createElement('canvas');
        tmp.width = w;
        tmp.height = h;
        const tctx = tmp.getContext('2d');
        tctx.setTransform(1, 0, 0, 1, 0, 0);
        tctx.drawImage(ctx.canvas, x, y, w, h, 0, 0, w, h);

        ctx.canvas.width = w;
        ctx.canvas.height = h;
        ctx.setTransform(1, 0, 0, 1, 0, 0);
        ctx.clearRect(0, 0, w, h);
        ctx.drawImage(tmp, 0, 0);
    }

    applyBrightness(ctx, factor) {
        const w = ctx.canvas.width;
        const h = ctx.canvas.height;
        const imgData = ctx.getImageData(0, 0, w, h);
        const data = imgData.data;
        for (let i = 0; i < data.length; i += 4) {
            data[i] = Math.min(255, Math.max(0, data[i] * factor));
            data[i + 1] = Math.min(255, Math.max(0, data[i + 1] * factor));
            data[i + 2] = Math.min(255, Math.max(0, data[i + 2] * factor));
        }
        ctx.putImageData(imgData, 0, 0);
    }

    applyContrast(ctx, factor) {
        const w = ctx.canvas.width;
        const h = ctx.canvas.height;
        const imgData = ctx.getImageData(0, 0, w, h);
        const data = imgData.data;
        const intercept = 128 * (1 - factor);
        for (let i = 0; i < data.length; i += 4) {
            data[i] = Math.min(255, Math.max(0, data[i] * factor + intercept));
            data[i + 1] = Math.min(255, Math.max(0, data[i + 1] * factor + intercept));
            data[i + 2] = Math.min(255, Math.max(0, data[i + 2] * factor + intercept));
        }
        ctx.putImageData(imgData, 0, 0);
    }

    applyMosaic(ctx, params) {
        const cellSize = params.cell_size || 10;
        const shape = params.shape || 'rect';
        let { x, y, width, height } = params;
        x = Math.max(0, Math.min(x, ctx.canvas.width));
        y = Math.max(0, Math.min(y, ctx.canvas.height));
        width = Math.max(1, Math.min(width, ctx.canvas.width - x));
        height = Math.max(1, Math.min(height, ctx.canvas.height - y));

        try {
            const region = ctx.getImageData(x, y, width, height);
            const cellsX = Math.max(1, Math.ceil(width / cellSize));
            const cellsY = Math.max(1, Math.ceil(height / cellSize));
            const smallW = cellsX;
            const smallH = cellsY;

            const small = document.createElement('canvas');
            small.width = smallW;
            small.height = smallH;
            const sctx = small.getContext('2d');
            sctx.imageSmoothingEnabled = false;
            sctx.clearRect(0, 0, smallW, smallH);

            for (let cy = 0; cy < cellsY; cy++) {
                for (let cx = 0; cx < cellsX; cx++) {
                    const sx = cx * cellSize;
                    const sy = cy * cellSize;
                    const sw = Math.min(cellSize, width - sx);
                    const sh = Math.min(cellSize, height - sy);
                    let r = 0, g = 0, b = 0, count = 0;
                    for (let py = 0; py < sh; py++) {
                        for (let px = 0; px < sw; px++) {
                            const idx = ((sy + py) * width + (sx + px)) * 4;
                            r += region.data[idx];
                            g += region.data[idx + 1];
                            b += region.data[idx + 2];
                            count++;
                        }
                    }
                    r = Math.round(r / count);
                    g = Math.round(g / count);
                    b = Math.round(b / count);
                    sctx.fillStyle = `rgb(${r},${g},${b})`;
                    sctx.fillRect(cx, cy, 1, 1);
                }
            }

            const scaled = document.createElement('canvas');
            scaled.width = width;
            scaled.height = height;
            const scctx = scaled.getContext('2d');
            scctx.imageSmoothingEnabled = false;
            scctx.drawImage(small, 0, 0, smallW, smallH, 0, 0, width, height);

            ctx.save();
            if (shape === 'circle') {
                const cx = x + width / 2;
                const cy = y + height / 2;
                const r = Math.min(width, height) / 2;
                ctx.beginPath();
                ctx.arc(cx, cy, r, 0, Math.PI * 2);
                ctx.clip();
            }
            ctx.drawImage(scaled, x, y);
            ctx.restore();
        } catch (e) {
            console.warn('Mosaic apply error', e);
        }
    }

    drawTempMosaic(ctx, rect) {
        ctx.save();
        ctx.strokeStyle = '#3b82f6';
        ctx.lineWidth = 2;
        ctx.setLineDash([5, 5]);
        if (rect.shape === 'circle') {
            const cx = rect.x + rect.width / 2;
            const cy = rect.y + rect.height / 2;
            const r = Math.min(rect.width, rect.height) / 2;
            ctx.beginPath();
            ctx.arc(cx, cy, r, 0, Math.PI * 2);
            ctx.stroke();
        } else {
            ctx.strokeRect(rect.x, rect.y, rect.width, rect.height);
        }
        ctx.restore();
    }

    drawCropOverlay() {
        const ctx = this.ctx;
        const { x, y, width, height } = this.cropBox;
        ctx.save();
        ctx.fillStyle = 'rgba(0, 0, 0, 0.5)';
        ctx.fillRect(0, 0, this.canvas.width, y);
        ctx.fillRect(0, y + height, this.canvas.width, this.canvas.height - y - height);
        ctx.fillRect(0, y, x, height);
        ctx.fillRect(x + width, y, this.canvas.width - x - width, height);

        ctx.strokeStyle = '#3b82f6';
        ctx.lineWidth = 2;
        ctx.setLineDash([]);
        ctx.strokeRect(x, y, width, height);

        const handleSize = 8;
        ctx.fillStyle = '#3b82f6';
        const corners = [
            [x, y], [x + width, y], [x, y + height], [x + width, y + height]
        ];
        corners.forEach(([cx, cy]) => {
            ctx.fillRect(cx - handleSize / 2, cy - handleSize / 2, handleSize, handleSize);
        });
        ctx.restore();
    }

    bindEvents() {
        document.querySelectorAll('.tool-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                this.setTool(btn.dataset.tool);
            });
        });

        document.getElementById('undoBtn').addEventListener('click', () => this.undo());
        document.getElementById('compareToggle').addEventListener('click', () => this.toggleCompare());
        document.getElementById('saveVersionBtn').addEventListener('click', () => this.saveVersion());
        document.getElementById('commitBtn').addEventListener('click', () => this.commitEdit());

        const exitBtn = document.getElementById('exitVersionPreviewBtn');
        if (exitBtn) {
            exitBtn.addEventListener('click', () => this.exitVersionPreview());
        }

        this.canvas.addEventListener('mousedown', e => this.onCanvasMouseDown(e));
        this.canvas.addEventListener('mousemove', e => this.onCanvasMouseMove(e));
        this.canvas.addEventListener('mouseup', e => this.onCanvasMouseUp(e));
        this.canvas.addEventListener('mouseleave', e => this.onCanvasMouseUp(e));

        this.bindVersionEvents();

        window.addEventListener('resize', () => {
            this.resetCanvasSize();
            this.render();
        });
    }

    bindVersionEvents() {
        document.querySelectorAll('.rollback-btn').forEach(btn => {
            btn.addEventListener('click', (e) => {
                e.stopPropagation();
                this.rollbackVersion(parseInt(btn.dataset.versionId));
            });
        });
        document.querySelectorAll('.preview-version-btn').forEach(btn => {
            btn.addEventListener('click', (e) => {
                e.stopPropagation();
                this.previewVersion(parseInt(btn.dataset.versionId));
            });
        });
    }

    getCanvasPoint(e) {
        const rect = this.canvas.getBoundingClientRect();
        const scaleX = this.canvas.width / rect.width;
        const scaleY = this.canvas.height / rect.height;
        return {
            x: (e.clientX - rect.left) * scaleX,
            y: (e.clientY - rect.top) * scaleY
        };
    }

    onCanvasMouseDown(e) {
        if (this.previewVersionId !== null) return;
        const pt = this.getCanvasPoint(e);

        if (this.currentTool === 'crop') {
            if (this.cropBox.active) {
                const handle = this.getCropHandle(pt);
                if (handle) {
                    this._cropDrag = { handle, startX: pt.x, startY: pt.y, origBox: { ...this.cropBox } };
                    return;
                }
                if (this.pointInBox(pt, this.cropBox)) {
                    this._cropDrag = { handle: 'move', startX: pt.x, startY: pt.y, origBox: { ...this.cropBox } };
                    return;
                }
            }
            this.cropBox = { x: pt.x, y: pt.y, width: 0, height: 0, active: true, ratio: this.cropBox.ratio };
            this._cropDrag = { handle: 'se', startX: pt.x, startY: pt.y, origBox: { ...this.cropBox } };
            this.render();
            return;
        }

        if (this.currentTool === 'mosaic-rect' || this.currentTool === 'mosaic-circle') {
            this.mosaicDrawing = true;
            this.mosaicStart = pt;
            const shape = this.currentTool === 'mosaic-circle' ? 'circle' : 'rect';
            this.tempMosaicRect = { x: pt.x, y: pt.y, width: 0, height: 0, shape, cellSize: this._mosaicCellSize || 15 };
            this.render();
        }
    }

    onCanvasMouseMove(e) {
        if (this.previewVersionId !== null) return;
        const pt = this.getCanvasPoint(e);

        if (this.currentTool === 'crop' && this._cropDrag) {
            this.updateCropBox(pt);
            this.render();
            return;
        }

        if (this.mosaicDrawing && this.mosaicStart && this.tempMosaicRect) {
            const start = this.mosaicStart;
            this.tempMosaicRect.x = Math.min(start.x, pt.x);
            this.tempMosaicRect.y = Math.min(start.y, pt.y);
            this.tempMosaicRect.width = Math.abs(pt.x - start.x);
            this.tempMosaicRect.height = Math.abs(pt.y - start.y);
            this.render();
        }
    }

    onCanvasMouseUp(e) {
        if (this.previewVersionId !== null) return;

        if (this.currentTool === 'crop' && this._cropDrag) {
            this._cropDrag = null;
            if (this.cropBox.width < 5 || this.cropBox.height < 5) {
                this.cropBox.width = 0;
                this.cropBox.height = 0;
            }
            this.render();
            this.updateToolSettings();
            return;
        }

        if (this.mosaicDrawing && this.tempMosaicRect) {
            this.mosaicDrawing = false;
            const rect = this.tempMosaicRect;
            if (rect.width > 5 && rect.height > 5) {
                this.addOperation('mosaic', {
                    shape: rect.shape,
                    cell_size: rect.cellSize,
                    x: Math.round(rect.x),
                    y: Math.round(rect.y),
                    width: Math.round(rect.width),
                    height: Math.round(rect.height)
                });
            }
            this.tempMosaicRect = null;
            this.mosaicStart = null;
            this.render();
        }
    }

    getCropHandle(pt) {
        const handleSize = 15;
        const { x, y, width, height } = this.cropBox;
        const corners = {
            nw: [x, y], ne: [x + width, y],
            sw: [x, y + height], se: [x + width, y + height]
        };
        for (const [name, [cx, cy]] of Object.entries(corners)) {
            if (Math.abs(pt.x - cx) < handleSize && Math.abs(pt.y - cy) < handleSize) {
                return name;
            }
        }
        return null;
    }

    pointInBox(pt, box) {
        return pt.x >= box.x && pt.x <= box.x + box.width &&
               pt.y >= box.y && pt.y <= box.y + box.height;
    }

    updateCropBox(pt) {
        if (!this._cropDrag) return;
        const { handle, startX, startY, origBox } = this._cropDrag;
        const dx = pt.x - startX;
        const dy = pt.y - startY;
        let x = origBox.x, y = origBox.y, w = origBox.width, h = origBox.height;
        const ratio = this.cropBox.ratio;

        if (handle === 'move') {
            x = origBox.x + dx;
            y = origBox.y + dy;
        } else {
            if (handle.includes('e')) w = origBox.width + dx;
            if (handle.includes('s')) h = origBox.height + dy;
            if (handle.includes('w')) { x = origBox.x + dx; w = origBox.width - dx; }
            if (handle.includes('n')) { y = origBox.y + dy; h = origBox.height - dy; }

            if (ratio && w > 0 && h > 0) {
                if (handle === 'e' || handle === 'w') {
                    h = w / ratio;
                } else if (handle === 'n' || handle === 's') {
                    w = h * ratio;
                } else {
                    const r1 = w / h;
                    if (r1 > ratio) w = h * ratio; else h = w / ratio;
                }
            }
        }

        if (w < 20) w = 20;
        if (h < 20) h = 20;
        if (x < 0) { x = 0; }
        if (y < 0) { y = 0; }
        if (x + w > this.canvas.width) w = this.canvas.width - x;
        if (y + h > this.canvas.height) h = this.canvas.height - y;
        if (ratio && w > 0 && h > 0) {
            if (w / h > ratio) w = h * ratio; else h = w / ratio;
        }

        this.cropBox.x = Math.max(0, x);
        this.cropBox.y = Math.max(0, y);
        this.cropBox.width = Math.max(20, Math.min(w, this.canvas.width - this.cropBox.x));
        this.cropBox.height = Math.max(20, Math.min(h, this.canvas.height - this.cropBox.y));
    }

    setTool(tool) {
        if (this.previewVersionId !== null && tool !== this.currentTool) {
            this.showToast('请先退出版本预览', 'warning');
            return;
        }

        if (this.previewOp) {
            this.previewOp = null;
        }

        this.currentTool = tool;
        document.querySelectorAll('.tool-btn').forEach(btn => {
            if (btn.dataset.tool === tool) {
                btn.classList.add('bg-primary', 'text-white');
                btn.classList.remove('bg-gray-50', 'text-gray-700');
            } else {
                btn.classList.remove('bg-primary', 'text-white');
                btn.classList.add('bg-gray-50', 'text-gray-700');
            }
        });

        if (tool === 'crop') {
            if (!this.cropBox.active || this.cropBox.width === 0) {
                this.cropBox = {
                    x: this.canvas.width * 0.1,
                    y: this.canvas.height * 0.1,
                    width: this.canvas.width * 0.8,
                    height: this.canvas.height * 0.8,
                    active: true,
                    ratio: null
                };
            }
        } else {
            this.cropBox.active = false;
        }

        this.canvas.style.cursor = (tool === 'crop' || tool.startsWith('mosaic')) ? 'crosshair' : 'default';
        this.updateToolSettings();
        this.render();
    }

    updateToolSettings() {
        const container = document.getElementById('toolSettings');
        const tool = this.currentTool;

        if (tool === 'rotate') {
            const defaultAngle = 0;
            container.innerHTML = `
                <h4 class="font-medium text-sm mb-3">旋转（拖动滑块实时预览）</h4>
                <div class="space-y-3">
                    <div>
                        <label class="text-xs text-gray-500 block mb-1">角度: <span id="angleValue">${defaultAngle}</span>°</label>
                        <input type="range" id="rotateSlider" min="-180" max="180" value="${defaultAngle}" step="1" class="w-full">
                    </div>
                    <div class="grid grid-cols-4 gap-2">
                        <button class="rotate-btn text-xs bg-gray-100 hover:bg-gray-200 py-1.5 rounded" data-angle="-90">-90°</button>
                        <button class="rotate-btn text-xs bg-gray-100 hover:bg-gray-200 py-1.5 rounded" data-angle="-15">-15°</button>
                        <button class="rotate-btn text-xs bg-gray-100 hover:bg-gray-200 py-1.5 rounded" data-angle="15">15°</button>
                        <button class="rotate-btn text-xs bg-gray-100 hover:bg-gray-200 py-1.5 rounded" data-angle="90">90°</button>
                    </div>
                    <div class="flex gap-2">
                        <button id="cancelRotate" class="flex-1 bg-gray-100 hover:bg-gray-200 text-gray-700 py-2 rounded text-sm">取消</button>
                        <button id="applyRotate" class="flex-1 bg-primary hover:bg-blue-600 text-white py-2 rounded text-sm">应用旋转</button>
                    </div>
                </div>
            `;
            const self = this;
            document.getElementById('rotateSlider').addEventListener('input', function () {
                const angle = parseInt(this.value) || 0;
                document.getElementById('angleValue').textContent = angle;
                if (angle === 0) {
                    self.previewOp = null;
                } else {
                    self.previewOp = { type: 'rotate', params: { angle } };
                }
                self.render();
            });
            document.querySelectorAll('.rotate-btn').forEach(btn => {
                btn.addEventListener('click', function () {
                    const angle = parseInt(this.dataset.angle);
                    document.getElementById('rotateSlider').value = angle;
                    document.getElementById('angleValue').textContent = angle;
                    self.previewOp = { type: 'rotate', params: { angle } };
                    self.render();
                });
            });
            document.getElementById('cancelRotate').addEventListener('click', () => {
                this.previewOp = null;
                document.getElementById('rotateSlider').value = 0;
                document.getElementById('angleValue').textContent = '0';
                this.render();
            });
            document.getElementById('applyRotate').addEventListener('click', () => {
                if (this.previewOp && this.previewOp.type === 'rotate') {
                    this.addOperation('rotate', { ...this.previewOp.params });
                    this.previewOp = null;
                    document.getElementById('rotateSlider').value = 0;
                    document.getElementById('angleValue').textContent = '0';
                }
            });
        } else if (tool === 'crop') {
            container.innerHTML = `
                <h4 class="font-medium text-sm mb-3">裁剪</h4>
                <div class="space-y-3">
                    <div>
                        <label class="text-xs text-gray-500 block mb-1">固定比例</label>
                        <div class="grid grid-cols-4 gap-2">
                            <button class="ratio-btn text-xs bg-gray-100 hover:bg-gray-200 py-1.5 rounded" data-ratio="free">自由</button>
                            <button class="ratio-btn text-xs bg-gray-100 hover:bg-gray-200 py-1.5 rounded" data-ratio="1">1:1</button>
                            <button class="ratio-btn text-xs bg-gray-100 hover:bg-gray-200 py-1.5 rounded" data-ratio="1.333">4:3</button>
                            <button class="ratio-btn text-xs bg-gray-100 hover:bg-gray-200 py-1.5 rounded" data-ratio="1.778">16:9</button>
                        </div>
                    </div>
                    <div class="text-xs text-gray-400">
                        当前: ${Math.round(this.cropBox.width)} × ${Math.round(this.cropBox.height)}px
                    </div>
                    <div class="flex gap-2">
                        <button id="resetCrop" class="flex-1 bg-gray-100 hover:bg-gray-200 text-gray-700 py-2 rounded text-sm">重置</button>
                        <button id="applyCrop" class="flex-1 bg-primary hover:bg-blue-600 text-white py-2 rounded text-sm">应用裁剪</button>
                    </div>
                </div>
            `;
            const self = this;
            document.querySelectorAll('.ratio-btn').forEach(btn => {
                btn.addEventListener('click', function () {
                    document.querySelectorAll('.ratio-btn').forEach(b => {
                        b.classList.remove('bg-primary', 'text-white');
                        b.classList.add('bg-gray-100');
                    });
                    this.classList.add('bg-primary', 'text-white');
                    this.classList.remove('bg-gray-100');
                    const r = this.dataset.ratio;
                    self.cropBox.ratio = r === 'free' ? null : parseFloat(r);
                    if (self.cropBox.ratio) {
                        const area = self.cropBox.width * self.cropBox.height;
                        const newH = Math.sqrt(area / self.cropBox.ratio);
                        const newW = newH * self.cropBox.ratio;
                        const cx = self.cropBox.x + self.cropBox.width / 2;
                        const cy = self.cropBox.y + self.cropBox.height / 2;
                        self.cropBox.width = Math.min(newW, self.canvas.width);
                        self.cropBox.height = Math.min(newH, self.canvas.height);
                        self.cropBox.x = Math.max(0, cx - self.cropBox.width / 2);
                        self.cropBox.y = Math.max(0, cy - self.cropBox.height / 2);
                        if (self.cropBox.x + self.cropBox.width > self.canvas.width) self.cropBox.x = self.canvas.width - self.cropBox.width;
                        if (self.cropBox.y + self.cropBox.height > self.canvas.height) self.cropBox.y = self.canvas.height - self.cropBox.height;
                    }
                    self.render();
                    self.updateToolSettings();
                });
            });
            document.getElementById('applyCrop').addEventListener('click', () => {
                if (this.cropBox.width > 10 && this.cropBox.height > 10) {
                    this.addOperation('crop', {
                        x: Math.round(this.cropBox.x),
                        y: Math.round(this.cropBox.y),
                        width: Math.round(this.cropBox.width),
                        height: Math.round(this.cropBox.height)
                    });
                    this.cropBox.active = false;
                }
            });
            document.getElementById('resetCrop').addEventListener('click', () => {
                this.cropBox = {
                    x: this.canvas.width * 0.1,
                    y: this.canvas.height * 0.1,
                    width: this.canvas.width * 0.8,
                    height: this.canvas.height * 0.8,
                    active: true,
                    ratio: this.cropBox.ratio
                };
                this.render();
                this.updateToolSettings();
            });
        } else if (tool === 'brightness') {
            const defaultVal = 100;
            container.innerHTML = `
                <h4 class="font-medium text-sm mb-3">亮度（拖动滑块实时预览）</h4>
                <div class="space-y-3">
                    <div>
                        <label class="text-xs text-gray-500 block mb-1">亮度: <span id="brightValue">${defaultVal}</span>%</label>
                        <input type="range" id="brightSlider" min="0" max="200" value="${defaultVal}" step="1" class="w-full">
                    </div>
                    <div class="grid grid-cols-3 gap-2">
                        <button class="bright-btn text-xs bg-gray-100 hover:bg-gray-200 py-1.5 rounded" data-val="80">暗</button>
                        <button class="bright-btn text-xs bg-gray-100 hover:bg-gray-200 py-1.5 rounded" data-val="100">原</button>
                        <button class="bright-btn text-xs bg-gray-100 hover:bg-gray-200 py-1.5 rounded" data-val="130">亮</button>
                    </div>
                    <div class="flex gap-2">
                        <button id="cancelBright" class="flex-1 bg-gray-100 hover:bg-gray-200 text-gray-700 py-2 rounded text-sm">取消</button>
                        <button id="applyBright" class="flex-1 bg-primary hover:bg-blue-600 text-white py-2 rounded text-sm">应用亮度</button>
                    </div>
                </div>
            `;
            const self = this;
            document.getElementById('brightSlider').addEventListener('input', function () {
                const v = parseInt(this.value);
                document.getElementById('brightValue').textContent = v;
                const factor = v / 100;
                if (Math.abs(factor - 1) < 0.001) {
                    self.previewOp = null;
                } else {
                    self.previewOp = { type: 'brightness', params: { value: factor } };
                }
                self.render();
            });
            document.querySelectorAll('.bright-btn').forEach(btn => {
                btn.addEventListener('click', function () {
                    const v = parseInt(this.dataset.val);
                    document.getElementById('brightSlider').value = v;
                    document.getElementById('brightValue').textContent = v;
                    const factor = v / 100;
                    self.previewOp = Math.abs(factor - 1) < 0.001 ? null : { type: 'brightness', params: { value: factor } };
                    self.render();
                });
            });
            document.getElementById('cancelBright').addEventListener('click', () => {
                this.previewOp = null;
                document.getElementById('brightSlider').value = 100;
                document.getElementById('brightValue').textContent = '100';
                this.render();
            });
            document.getElementById('applyBright').addEventListener('click', () => {
                if (this.previewOp && this.previewOp.type === 'brightness') {
                    this.addOperation('brightness', { ...this.previewOp.params });
                    this.previewOp = null;
                    document.getElementById('brightSlider').value = 100;
                    document.getElementById('brightValue').textContent = '100';
                }
            });
        } else if (tool === 'contrast') {
            const defaultVal = 100;
            container.innerHTML = `
                <h4 class="font-medium text-sm mb-3">对比度（拖动滑块实时预览）</h4>
                <div class="space-y-3">
                    <div>
                        <label class="text-xs text-gray-500 block mb-1">对比度: <span id="contrastValue">${defaultVal}</span>%</label>
                        <input type="range" id="contrastSlider" min="0" max="200" value="${defaultVal}" step="1" class="w-full">
                    </div>
                    <div class="grid grid-cols-3 gap-2">
                        <button class="contrast-btn text-xs bg-gray-100 hover:bg-gray-200 py-1.5 rounded" data-val="70">低</button>
                        <button class="contrast-btn text-xs bg-gray-100 hover:bg-gray-200 py-1.5 rounded" data-val="100">原</button>
                        <button class="contrast-btn text-xs bg-gray-100 hover:bg-gray-200 py-1.5 rounded" data-val="150">高</button>
                    </div>
                    <div class="flex gap-2">
                        <button id="cancelContrast" class="flex-1 bg-gray-100 hover:bg-gray-200 text-gray-700 py-2 rounded text-sm">取消</button>
                        <button id="applyContrast" class="flex-1 bg-primary hover:bg-blue-600 text-white py-2 rounded text-sm">应用对比度</button>
                    </div>
                </div>
            `;
            const self = this;
            document.getElementById('contrastSlider').addEventListener('input', function () {
                const v = parseInt(this.value);
                document.getElementById('contrastValue').textContent = v;
                const factor = v / 100;
                if (Math.abs(factor - 1) < 0.001) {
                    self.previewOp = null;
                } else {
                    self.previewOp = { type: 'contrast', params: { value: factor } };
                }
                self.render();
            });
            document.querySelectorAll('.contrast-btn').forEach(btn => {
                btn.addEventListener('click', function () {
                    const v = parseInt(this.dataset.val);
                    document.getElementById('contrastSlider').value = v;
                    document.getElementById('contrastValue').textContent = v;
                    const factor = v / 100;
                    self.previewOp = Math.abs(factor - 1) < 0.001 ? null : { type: 'contrast', params: { value: factor } };
                    self.render();
                });
            });
            document.getElementById('cancelContrast').addEventListener('click', () => {
                this.previewOp = null;
                document.getElementById('contrastSlider').value = 100;
                document.getElementById('contrastValue').textContent = '100';
                this.render();
            });
            document.getElementById('applyContrast').addEventListener('click', () => {
                if (this.previewOp && this.previewOp.type === 'contrast') {
                    this.addOperation('contrast', { ...this.previewOp.params });
                    this.previewOp = null;
                    document.getElementById('contrastSlider').value = 100;
                    document.getElementById('contrastValue').textContent = '100';
                }
            });
        } else if (tool === 'mosaic-rect' || tool === 'mosaic-circle') {
            const shape = tool === 'mosaic-circle' ? '圆形' : '矩形';
            container.innerHTML = `
                <h4 class="font-medium text-sm mb-3">${shape}打码</h4>
                <div class="space-y-3">
                    <p class="text-xs text-gray-500">在图片上按住鼠标拖动画出打码区域</p>
                    <div>
                        <label class="text-xs text-gray-500 block mb-1">像素块大小: <span id="cellValue">${this._mosaicCellSize}</span>px</label>
                        <input type="range" id="cellSlider" min="5" max="50" value="${this._mosaicCellSize}" step="1" class="w-full">
                    </div>
                </div>
            `;
            const self = this;
            document.getElementById('cellSlider').addEventListener('input', function () {
                document.getElementById('cellValue').textContent = this.value;
                self._mosaicCellSize = parseInt(this.value);
            });
        } else {
            container.innerHTML = '<p class="text-sm text-gray-400 text-center py-4">选择上方工具进行调整</p>';
        }
    }

    addOperation(type, params) {
        this.operations.push({ type, params });
        this.updateOperationsList();
        this.render();
    }

    undo() {
        if (this.previewVersionId !== null) {
            this.showToast('请先退出版本预览', 'warning');
            return;
        }
        if (this.previewOp) {
            this.previewOp = null;
            this.updateToolSettings();
            this.render();
            return;
        }
        if (this.operations.length > 0) {
            this.operations.pop();
            this.updateOperationsList();
            this.render();
        }
    }

    updateUndoState() {
        const btn = document.getElementById('undoBtn');
        if (btn) btn.disabled = (this.operations.length === 0 && !this.previewOp);
    }

    updateOperationsList() {
        document.getElementById('opsCount').textContent = this.operations.length;
        const container = document.getElementById('opsListContent');
        if (this.operations.length === 0) {
            container.innerHTML = '<p class="text-xs text-gray-400 text-center py-4">暂无操作</p>';
            return;
        }
        const typeNames = {
            rotate: '旋转',
            crop: '裁剪',
            brightness: '亮度',
            contrast: '对比度',
            mosaic: '马赛克'
        };
        container.innerHTML = this.operations.map((op, i) => `
            <div class="flex items-center justify-between px-2 py-1.5 text-xs bg-gray-50 rounded">
                <span class="text-gray-700">${i + 1}. ${typeNames[op.type] || op.type}</span>
                <button class="text-red-400 hover:text-red-600 undo-one" data-idx="${i}">×</button>
            </div>
        `).join('');
        container.querySelectorAll('.undo-one').forEach(btn => {
            btn.addEventListener('click', () => {
                if (this.previewVersionId !== null) return;
                const idx = parseInt(btn.dataset.idx);
                this.operations.splice(idx, 1);
                this.updateOperationsList();
                this.render();
            });
        });
    }

    toggleCompare() {
        this.compareMode = !this.compareMode;
        const overlay = document.getElementById('compareOverlay');
        const btn = document.getElementById('compareToggle');
        if (this.compareMode) {
            overlay.classList.remove('hidden');
            overlay.style.display = 'block';
            btn.classList.add('bg-primary', 'text-white');
            btn.classList.remove('bg-white', 'text-gray-700');
        } else {
            overlay.classList.add('hidden');
            overlay.style.display = 'none';
            btn.classList.remove('bg-primary', 'text-white');
            btn.classList.add('bg-white', 'text-gray-700');
        }
    }

    async saveVersion() {
        if (this.previewVersionId !== null) {
            this.showToast('请先退出版本预览', 'warning');
            return;
        }
        const { value: label } = await Swal.fire({
            title: '保存版本',
            input: 'text',
            inputLabel: '版本名称',
            inputValue: `版本 ${new Date().toLocaleString()}`,
            showCancelButton: true,
            confirmButtonText: '保存',
            cancelButtonText: '取消',
            confirmButtonColor: '#3b82f6'
        });
        if (!label) return;

        let thumbnail = '';
        try {
            const thumb = document.createElement('canvas');
            const scale = Math.min(200 / this.canvas.width, 1);
            thumb.width = Math.round(this.canvas.width * scale);
            thumb.height = Math.round(this.canvas.height * scale);
            thumb.getContext('2d').drawImage(this.canvas, 0, 0, thumb.width, thumb.height);
            thumbnail = thumb.toDataURL('image/jpeg', 0.7);
        } catch (e) {}

        try {
            const r = await fetch(`/api/photo/${window.PHOTO_ID}/version`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ operations: this.operations, label, thumbnail })
            });
            const data = await r.json();
            if (data.success) {
                this.versionsCache[data.version.id] = data.version;
                this.showToast('版本已保存', 'success');
                this.refreshVersionsList();
            } else {
                this.showToast(data.message || '保存失败', 'error');
            }
        } catch (e) {
            this.showToast('网络错误', 'error');
        }
    }

    async refreshVersionsList() {
        try {
            const r = await fetch(`/api/photo/${window.PHOTO_ID}/versions`);
            const data = await r.json();
            if (data.success) {
                const container = document.getElementById('versionsList');
                if (data.versions.length === 0) {
                    container.innerHTML = '<p class="text-xs text-gray-400 text-center py-4">暂无历史版本</p>';
                    return;
                }
                data.versions.forEach(v => {
                    this.versionsCache[v.id] = v;
                });
                container.innerHTML = data.versions.map(v => `
                    <div class="version-item p-2 rounded-lg border border-gray-100 hover:bg-gray-50 transition ${this.previewVersionId === v.id ? 'bg-amber-50 border-amber-200' : ''}" data-version-id="${v.id}">
                        <div class="flex items-start gap-2">
                            ${v.thumbnail
                                ? `<div class="w-12 h-12 flex-shrink-0 rounded overflow-hidden bg-gray-100 border border-gray-200">
                                     <img src="${v.thumbnail}" class="w-full h-full object-cover version-thumb">
                                   </div>`
                                : `<div class="w-12 h-12 flex-shrink-0 rounded bg-gray-100 border border-gray-200 flex items-center justify-center">
                                     <svg class="w-6 h-6 text-gray-300" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z"></path></svg>
                                   </div>`}
                            <div class="flex-1 min-w-0">
                                <div class="text-sm font-medium text-gray-800 truncate">${v.label}</div>
                                <div class="text-xs text-gray-400">${v.created_at}</div>
                                <div class="flex items-center gap-2 mt-1">
                                    <button class="preview-version-btn text-xs text-blue-500 hover:text-blue-700 hover:underline ${this.previewVersionId === v.id ? 'font-bold' : ''}" data-version-id="${v.id}">
                                        ${this.previewVersionId === v.id ? '当前预览中' : '预览'}
                                    </button>
                                    <span class="text-gray-200">|</span>
                                    <button class="rollback-btn text-xs text-primary hover:underline" data-version-id="${v.id}">回滚</button>
                                </div>
                            </div>
                        </div>
                    </div>
                `).join('');
                this.bindVersionEvents();
            }
        } catch (e) {}
    }

    previewVersion(versionId) {
        if (this.previewVersionId === versionId) return;

        if (this.previewOp) {
            this.previewOp = null;
            this.updateToolSettings();
        }

        const version = this.versionsCache[versionId];
        if (!version) {
            this.showToast('版本数据未找到', 'error');
            return;
        }

        if (this.previewVersionId === null) {
            this.savedOperationsBeforePreview = [...this.operations];
            this.savedPreviewOpBeforePreview = this.previewOp;
        }

        this.previewVersionId = versionId;
        this.operations = version.operations || [];

        const banner = document.getElementById('versionPreviewBanner');
        if (banner) {
            banner.classList.remove('hidden');
            banner.classList.add('flex');
        }
        const nameEl = document.getElementById('previewVersionName');
        if (nameEl) nameEl.textContent = version.label || `版本 ${versionId}`;

        this.updateOperationsList();
        this.refreshVersionsList();
        this.render();
    }

    exitVersionPreview() {
        if (this.previewVersionId === null) return;

        if (this.savedOperationsBeforePreview !== null) {
            this.operations = this.savedOperationsBeforePreview;
        }
        if (this.savedPreviewOpBeforePreview !== null) {
            this.previewOp = this.savedPreviewOpBeforePreview;
        }

        this.previewVersionId = null;
        this.savedOperationsBeforePreview = null;
        this.savedPreviewOpBeforePreview = null;

        const banner = document.getElementById('versionPreviewBanner');
        if (banner) {
            banner.classList.add('hidden');
            banner.classList.remove('flex');
        }

        this.updateOperationsList();
        this.refreshVersionsList();
        this.updateToolSettings();
        this.render();
        this.showToast('已退出版本预览，恢复当前编辑', 'success');
    }

    async rollbackVersion(versionId) {
        const version = this.versionsCache[versionId];
        const result = await Swal.fire({
            title: '回滚到该版本？',
            html: `将使用版本「<b>${version ? version.label : versionId}</b>」的操作序列替换当前编辑<br><span class="text-amber-600 text-xs">（如需先看看效果请点「预览」按钮）</span>`,
            icon: 'question',
            showCancelButton: true,
            confirmButtonText: '确定回滚',
            cancelButtonText: '取消',
            confirmButtonColor: '#3b82f6'
        });
        if (!result.isConfirmed) return;

        try {
            const r = await fetch(`/api/photo/${window.PHOTO_ID}/version/${versionId}/rollback`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' }
            });
            const data = await r.json();
            if (data.success) {
                this.operations = data.operations || [];
                this.previewOp = null;
                this.previewVersionId = null;
                this.savedOperationsBeforePreview = null;
                this.savedPreviewOpBeforePreview = null;

                const banner = document.getElementById('versionPreviewBanner');
                if (banner) {
                    banner.classList.add('hidden');
                    banner.classList.remove('flex');
                }

                this.updateOperationsList();
                this.refreshVersionsList();
                this.updateToolSettings();
                this.render();
                this.showToast('已回滚到该版本', 'success');
            } else {
                this.showToast(data.message || '回滚失败', 'error');
            }
        } catch (e) {
            this.showToast('网络错误', 'error');
        }
    }

    async commitEdit() {
        if (this.previewVersionId !== null) {
            const r = await Swal.fire({
                title: '正在预览历史版本',
                text: '请先退出版本预览后再保存，确认退出预览并保存当前编辑？',
                icon: 'warning',
                showCancelButton: true,
                confirmButtonText: '退出预览并保存',
                cancelButtonText: '取消',
                confirmButtonColor: '#3b82f6'
            });
            if (!r.isConfirmed) return;
            this.exitVersionPreview();
        }

        if (this.previewOp) {
            const r = await Swal.fire({
                title: '有未应用的调整',
                text: '当前预览中的调整还未加入操作列表，是否先应用后保存？',
                showDenyButton: true,
                showCancelButton: true,
                confirmButtonText: '应用并保存',
                denyButtonText: '丢弃调整，直接保存',
                cancelButtonText: '取消',
                confirmButtonColor: '#3b82f6'
            });
            if (r.isConfirmed) {
                this.addOperation(this.previewOp.type, { ...this.previewOp.params });
                this.previewOp = null;
            } else if (r.isDenied) {
                this.previewOp = null;
            } else {
                return;
            }
        }

        const result = await Swal.fire({
            title: '确认保存编辑结果？',
            text: '将合成编辑结果并覆盖原始图片文件，原图备份保留',
            icon: 'warning',
            showCancelButton: true,
            confirmButtonText: '确认保存',
            cancelButtonText: '取消',
            confirmButtonColor: '#3b82f6'
        });
        if (!result.isConfirmed) return;

        try {
            const r = await fetch(`/api/photo/${window.PHOTO_ID}/commit`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ operations: this.operations })
            });
            const data = await r.json();
            if (data.success) {
                this.showToast('编辑结果已保存', 'success');
                setTimeout(() => {
                    if (window.ALBUM_ID) {
                        window.location.href = `/album/${window.ALBUM_ID}`;
                    } else {
                        window.history.back();
                    }
                }, 1000);
            } else {
                this.showToast(data.message || '保存失败', 'error');
            }
        } catch (e) {
            this.showToast('网络错误', 'error');
        }
    }

    showToast(message, type = 'success') {
        const Toast = Swal.mixin({
            toast: true,
            position: 'top',
            showConfirmButton: false,
            timer: 2500,
            timerProgressBar: true
        });
        Toast.fire({ icon: type, title: message });
    }
}

document.addEventListener('DOMContentLoaded', () => {
    window.photoEditor = new PhotoEditor();
});
