/**
 * Post background color picker: HSV plane (canvas), hue strip, live preview callback.
 * No <input type="color">, no external libraries.
 */
(function (global) {
    'use strict';

    function clamp(n, a, b) {
        return Math.max(a, Math.min(b, n));
    }

    function parseHex(hex) {
        if (!hex || typeof hex !== 'string') return { r: 255, g: 255, b: 255 };
        var s = hex.replace(/^#/, '').trim();
        if (s.length === 3) {
            s = s.split('').map(function (c) { return c + c; }).join('');
        }
        if (s.length !== 6 || /[^0-9a-f]/i.test(s)) {
            return { r: 255, g: 255, b: 255 };
        }
        var n = parseInt(s, 16);
        return { r: (n >> 16) & 255, g: (n >> 8) & 255, b: n & 255 };
    }

    function rgbToHex(r, g, b) {
        return (
            '#' +
            [r, g, b]
                .map(function (x) {
                    var h = clamp(Math.round(x), 0, 255).toString(16);
                    return h.length === 1 ? '0' + h : h;
                })
                .join('')
        );
    }

    function hsvToRgb(h, s, v) {
        h = ((h % 360) + 360) % 360;
        var c = v * s;
        var x = c * (1 - Math.abs(((h / 60) % 2) - 1));
        var m = v - c;
        var rp, gp, bp;
        if (h < 60) {
            rp = c;
            gp = x;
            bp = 0;
        } else if (h < 120) {
            rp = x;
            gp = c;
            bp = 0;
        } else if (h < 180) {
            rp = 0;
            gp = c;
            bp = x;
        } else if (h < 240) {
            rp = 0;
            gp = x;
            bp = c;
        } else if (h < 300) {
            rp = x;
            gp = 0;
            bp = c;
        } else {
            rp = c;
            gp = 0;
            bp = x;
        }
        return {
            r: Math.round((rp + m) * 255),
            g: Math.round((gp + m) * 255),
            b: Math.round((bp + m) * 255),
        };
    }

    function rgbToHsv(r, g, b) {
        r /= 255;
        g /= 255;
        b /= 255;
        var max = Math.max(r, g, b);
        var min = Math.min(r, g, b);
        var d = max - min;
        var h = 0;
        var s = max === 0 ? 0 : d / max;
        var v = max;
        if (d > 1e-10) {
            if (max === r) h = 60 * (((g - b) / d) % 6);
            else if (max === g) h = 60 * ((b - r) / d + 2);
            else h = 60 * ((r - g) / d + 4);
        }
        if (h < 0) h += 360;
        return { h: h, s: s, v: v };
    }

    function hexToHsv(hex) {
        var rgb = parseHex(hex);
        return rgbToHsv(rgb.r, rgb.g, rgb.b);
    }

    /** Paint SV plane for fixed hue */
    function drawSvCanvas(canvas, h) {
        var w = canvas.width;
        var hgt = canvas.height;
        var ctx = canvas.getContext('2d');
        var img = ctx.createImageData(w, hgt);
        var data = img.data;
        var i = 0;
        for (var y = 0; y < hgt; y++) {
            var v = 1 - y / (hgt - 1 || 1);
            for (var x = 0; x < w; x++) {
                var s = x / (w - 1 || 1);
                var rgb = hsvToRgb(h, s, v);
                data[i++] = rgb.r;
                data[i++] = rgb.g;
                data[i++] = rgb.b;
                data[i++] = 255;
            }
        }
        ctx.putImageData(img, 0, 0);
    }

    /**
     * @param {HTMLElement} container
     * @param {{ initialHex?: string, onChange?: (hex: string) => void }} options
     */
    function createPostBgColorPicker(container, options) {
        options = options || {};
        var onChange = typeof options.onChange === 'function' ? options.onChange : function () {};

        var initial = hexToHsv(options.initialHex || '#ffffff');
        var hsv = { h: initial.h, s: initial.s, v: initial.v };

        var root = document.createElement('div');
        root.className = 'ccp-root';

        var svWrap = document.createElement('div');
        svWrap.className = 'ccp-sv-wrap';
        var canvas = document.createElement('canvas');
        canvas.className = 'ccp-sv-canvas';
        canvas.width = 220;
        canvas.height = 180;
        var svMarker = document.createElement('button');
        svMarker.type = 'button';
        svMarker.className = 'ccp-sv-marker';
        svMarker.setAttribute('aria-label', 'Saturation and brightness');
        svWrap.appendChild(canvas);
        svWrap.appendChild(svMarker);

        var mid = document.createElement('div');
        mid.className = 'ccp-mid';

        var preview = document.createElement('div');
        preview.className = 'ccp-preview';

        var hueWrap = document.createElement('div');
        hueWrap.className = 'ccp-hue-wrap';
        var hueTrack = document.createElement('div');
        hueTrack.className = 'ccp-hue-track';
        var hueThumb = document.createElement('button');
        hueThumb.type = 'button';
        hueThumb.className = 'ccp-hue-thumb';
        hueThumb.setAttribute('aria-label', 'Hue');
        hueTrack.appendChild(hueThumb);
        hueWrap.appendChild(hueTrack);

        mid.appendChild(preview);
        mid.appendChild(hueWrap);

        root.appendChild(svWrap);
        root.appendChild(mid);
        container.appendChild(root);

        function currentRgb() {
            return hsvToRgb(hsv.h, hsv.s, hsv.v);
        }

        function currentHex() {
            var rgb = currentRgb();
            return rgbToHex(rgb.r, rgb.g, rgb.b);
        }

        function updateSvMarker() {
            svMarker.style.left = hsv.s * 100 + '%';
            svMarker.style.top = (1 - hsv.v) * 100 + '%';
        }

        function updateHueThumb() {
            hueThumb.style.left = (hsv.h / 360) * 100 + '%';
        }

        function paint() {
            drawSvCanvas(canvas, hsv.h);
            preview.style.backgroundColor = currentHex();
            var hueOnly = hsvToRgb(hsv.h, 1, 1);
            hueThumb.style.backgroundColor = rgbToHex(hueOnly.r, hueOnly.g, hueOnly.b);
            updateSvMarker();
            updateHueThumb();
        }

        function commit() {
            paint();
            onChange(currentHex());
        }

        var rafId = null;
        function scheduleCommit() {
            if (rafId) return;
            rafId = window.requestAnimationFrame(function () {
                rafId = null;
                commit();
            });
        }

        /**
         * @param {string} hex
         * @param {boolean} [silent] true = только UI, без onChange
         */
        function setFromHex(hex, silent) {
            if (rafId) {
                window.cancelAnimationFrame(rafId);
                rafId = null;
            }
            var next = hexToHsv(hex);
            if (next.s > 0.001) hsv.h = next.h;
            hsv.s = next.s;
            hsv.v = next.v;
            if (silent) paint();
            else commit();
        }

        function setSvFromClient(clientX, clientY) {
            var rect = canvas.getBoundingClientRect();
            var x = clamp((clientX - rect.left) / rect.width, 0, 1);
            var y = clamp((clientY - rect.top) / rect.height, 0, 1);
            hsv.s = x;
            hsv.v = 1 - y;
            scheduleCommit();
        }

        function setHueFromClient(clientX) {
            var rect = hueTrack.getBoundingClientRect();
            var t = clamp((clientX - rect.left) / rect.width, 0, 1);
            hsv.h = t * 360;
            scheduleCommit();
        }

        var activeDrag = null; // { mode: 'sv'|'hue', pointerId: number }
        var supportsPointer = !!window.PointerEvent;

        function setActiveDrag(mode, pointerId, target) {
            activeDrag = { mode: mode, pointerId: pointerId };
            if (target && typeof target.setPointerCapture === 'function') {
                try {
                    target.setPointerCapture(pointerId);
                } catch (err) {
                    // Some environments may throw; dragging still works via document listeners.
                }
            }
        }

        function clearActiveDrag() {
            activeDrag = null;
        }

        function onSvDown(e) {
            if (e.pointerType === 'mouse' && typeof e.button === 'number' && e.button !== 0) return;
            e.preventDefault();
            setActiveDrag('sv', e.pointerId, e.currentTarget);
            setSvFromClient(e.clientX, e.clientY);
        }

        function onHueDown(e) {
            if (e.pointerType === 'mouse' && typeof e.button === 'number' && e.button !== 0) return;
            e.preventDefault();
            setActiveDrag('hue', e.pointerId, e.currentTarget);
            setHueFromClient(e.clientX);
        }

        function bindPointerPath() {
            canvas.addEventListener('pointerdown', onSvDown);
            svMarker.addEventListener('pointerdown', onSvDown);
            hueTrack.addEventListener('pointerdown', onHueDown);
            hueThumb.addEventListener('pointerdown', function (e) {
                e.stopPropagation();
                onHueDown(e);
            });
            document.addEventListener('pointermove', onDocMove);
            document.addEventListener('pointerup', onDocUp);
            document.addEventListener('pointercancel', onDocUp);
        }

        function normalizeTouchPoint(e) {
            var t = (e.touches && e.touches[0]) || (e.changedTouches && e.changedTouches[0]);
            if (!t) return null;
            return { clientX: t.clientX, clientY: t.clientY };
        }

        function onSvTouchStart(e) {
            var p = normalizeTouchPoint(e);
            if (!p) return;
            if (e.cancelable) e.preventDefault();
            setActiveDrag('sv', -1, null);
            setSvFromClient(p.clientX, p.clientY);
        }

        function onHueTouchStart(e) {
            var p = normalizeTouchPoint(e);
            if (!p) return;
            if (e.cancelable) e.preventDefault();
            setActiveDrag('hue', -1, null);
            setHueFromClient(p.clientX);
        }

        function onDocTouchMove(e) {
            if (!activeDrag || activeDrag.pointerId !== -1) return;
            var p = normalizeTouchPoint(e);
            if (!p) return;
            if (e.cancelable) e.preventDefault();
            if (activeDrag.mode === 'sv') setSvFromClient(p.clientX, p.clientY);
            else if (activeDrag.mode === 'hue') setHueFromClient(p.clientX);
        }

        function onDocTouchEnd(e) {
            if (!activeDrag || activeDrag.pointerId !== -1) return;
            clearActiveDrag();
            if (e.cancelable) e.preventDefault();
        }

        function bindTouchFallbackPath() {
            canvas.addEventListener('touchstart', onSvTouchStart, { passive: false });
            svMarker.addEventListener('touchstart', onSvTouchStart, { passive: false });
            hueTrack.addEventListener('touchstart', onHueTouchStart, { passive: false });
            hueThumb.addEventListener('touchstart', function (e) {
                e.stopPropagation();
                onHueTouchStart(e);
            }, { passive: false });
            document.addEventListener('touchmove', onDocTouchMove, { passive: false });
            document.addEventListener('touchend', onDocTouchEnd, { passive: false });
            document.addEventListener('touchcancel', onDocTouchEnd, { passive: false });
        }

        function onDocMove(e) {
            if (!activeDrag || activeDrag.pointerId !== e.pointerId) return;
            if (e.cancelable) e.preventDefault();
            if (activeDrag.mode === 'sv') {
                setSvFromClient(e.clientX, e.clientY);
            } else if (activeDrag.mode === 'hue') {
                setHueFromClient(e.clientX);
            }
        }

        function onDocUp(e) {
            if (!activeDrag || activeDrag.pointerId !== e.pointerId) return;
            clearActiveDrag();
        }

        if (supportsPointer) bindPointerPath();
        else bindTouchFallbackPath();

        function onResize() {
            paint();
        }
        window.addEventListener('resize', onResize);

        paint();
        onChange(currentHex());

        return {
            setHex: function (hex, silent) {
                setFromHex(hex, silent);
            },
            getHex: currentHex,
            destroy: function () {
                if (supportsPointer) {
                    document.removeEventListener('pointermove', onDocMove);
                    document.removeEventListener('pointerup', onDocUp);
                    document.removeEventListener('pointercancel', onDocUp);
                } else {
                    document.removeEventListener('touchmove', onDocTouchMove);
                    document.removeEventListener('touchend', onDocTouchEnd);
                    document.removeEventListener('touchcancel', onDocTouchEnd);
                }
                if (rafId) {
                    window.cancelAnimationFrame(rafId);
                    rafId = null;
                }
                window.removeEventListener('resize', onResize);
                if (root.parentNode) root.parentNode.removeChild(root);
            },
        };
    }

    global.createPostBgColorPicker = createPostBgColorPicker;
})(typeof window !== 'undefined' ? window : this);
