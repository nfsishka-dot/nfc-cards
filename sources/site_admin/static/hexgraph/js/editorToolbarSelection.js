/**
 * Сохранение/восстановление выделения при кликах по тулбару Quill.
 * Вынесено из шаблона: версия в URL (?v=…) даёт гарантированный cache-bust после collectstatic.
 */
(function (global) {
    global.hexgraphSetupToolbarSelectionPreservation = function (quill) {
        function getToolbar() {
            return document.querySelector('form .ql-toolbar') ||
                document.querySelector('.editor-shell .ql-toolbar') ||
                document.querySelector('#editor-container .ql-toolbar') ||
                document.querySelector('.ql-toolbar');
        }
        var toolbar = getToolbar();
        if (!toolbar || !quill) return;
        var coarsePointer = (window.matchMedia && window.matchMedia('(pointer: coarse)').matches) || ('ontouchstart' in window);

        function closeMobileKeyboardIfNeeded() {
            if (!coarsePointer) return;
            var ae = document.activeElement;
            if (ae && typeof ae.blur === 'function') ae.blur();
            if (quill.root && typeof quill.root.blur === 'function') quill.root.blur();
        }

        function shouldDismissKeyboardForTarget(t) {
            if (!t || !t.closest) return false;
            return !!(t.closest('.ql-post-bg-picker') || t.closest('.ql-post-bg-popover'));
        }

        function shouldSaveSelectionTarget(t) {
            if (!t || !toolbar.contains(t)) return false;
            if (t.closest && t.closest('.ql-post-help')) return false;
            if (t.closest && t.closest('.hg-help-modal')) return false;
            if (t.closest('.ql-toolbar-tools button')) return true;
            if (t.closest('.ql-picker-label')) return true;
            if (t.closest('.ql-picker-item')) return true;
            if (t.closest('.ql-post-bg-picker')) return true;
            if (t.closest('.ql-post-bg-popover')) return true;
            return false;
        }

        function shouldSkipRestoreForMenuOpenClick(t) {
            if (!t || !t.closest) return false;
            if (t.closest('.ql-post-bg-picker')) return true;
            var picker = t.closest('.ql-picker');
            if (picker && !t.closest('.ql-picker-item')) return true;
            return false;
        }

        function saveRange() {
            var sel = quill.getSelection();
            if (sel && typeof sel.index === 'number') {
                toolbar._hgToolbarSel = { index: sel.index, length: sel.length || 0 };
            }
        }

        function restoreRange() {
            var r = toolbar._hgToolbarSel;
            if (!r) return;
            toolbar._hgToolbarSel = null;
            if (typeof quill._hgUnlockMobileKbFocus === 'function') {
                quill._hgUnlockMobileKbFocus();
            }
            var len = quill.getLength();
            var idx = Math.max(0, Math.min(r.index, Math.max(0, len - 1)));
            var L = r.length > 0 ? r.length : 0;
            try {
                quill.setSelection(idx, L, 'user');
                if (!toolbar._hgSkipFocusRestore) {
                    if (quill._hgMobileFocus && typeof quill._hgMobileFocus.canFocus === 'function' && !quill._hgMobileFocus.canFocus()) {
                        if (typeof quill._hgUnlockMobileKbFocus === 'function') quill._hgUnlockMobileKbFocus();
                    }
                    quill.focus();
                }
            } catch (_e) {}
            toolbar._hgSkipFocusRestore = false;
        }

        function scheduleRestoreSavedSelection() {
            if (!toolbar._hgToolbarSel) return;
            requestAnimationFrame(function () {
                requestAnimationFrame(restoreRange);
            });
        }
        toolbar._hgScheduleRestoreSavedSelection = scheduleRestoreSavedSelection;

        toolbar.addEventListener('mousedown', function (e) {
            if (e.button !== 0) return;
            if (!shouldSaveSelectionTarget(e.target)) return;
            if (coarsePointer) {
                toolbar._hgSkipFocusRestore = true;
            }
            saveRange();
            if (coarsePointer && shouldDismissKeyboardForTarget(e.target)) {
                closeMobileKeyboardIfNeeded();
            }
        }, true);

        toolbar.addEventListener('click', function (e) {
            if (!shouldSaveSelectionTarget(e.target)) return;
            if (!toolbar._hgToolbarSel) return;
            if (shouldSkipRestoreForMenuOpenClick(e.target)) return;
            scheduleRestoreSavedSelection();
        }, true);

        toolbar.addEventListener('touchstart', function (e) {
            if (!shouldSaveSelectionTarget(e.target)) return;
            toolbar._hgSkipFocusRestore = true;
            saveRange();
            if (shouldDismissKeyboardForTarget(e.target)) {
                closeMobileKeyboardIfNeeded();
            }
        }, { capture: true, passive: true });

        toolbar.addEventListener('touchend', function (e) {
            if (!shouldSaveSelectionTarget(e.target)) return;
            if (!toolbar._hgToolbarSel) return;
            if (shouldSkipRestoreForMenuOpenClick(e.target)) return;
            scheduleRestoreSavedSelection();
        }, { capture: true, passive: true });
    };
})(typeof window !== 'undefined' ? window : this);
