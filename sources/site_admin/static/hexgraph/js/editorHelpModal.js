/**
 * Центрированная модалка справки по кнопкам тулбара Quill.
 * Иконки — клоны реальных узлов из .ql-toolbar (визуальное совпадение с редактором).
 */
(function (global) {
    'use strict';

    var CLS_ROOT = 'hg-help-modal';
    var CLS_OPEN = 'hg-help-open';

    function mount(options) {
        options = options || {};
        var toolbarSelector = options.toolbarSelector || 'form .ql-toolbar';
        var toolbar = document.querySelector(toolbarSelector);
        if (!toolbar) return;

        if (toolbar.getAttribute('data-hg-help-mounted') === '1') return;
        toolbar.setAttribute('data-hg-help-mounted', '1');

        var fmt = document.createElement('span');
        fmt.className = 'ql-formats';
        var btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'ql-post-help';
        btn.setAttribute('aria-label', 'Справка по редактору');
        btn.setAttribute('title', 'Справка');
        btn.setAttribute('aria-haspopup', 'dialog');
        btn.innerHTML =
            '<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' +
            '<circle cx="12" cy="12" r="9"></circle>' +
            '<path d="M9.6 9.3a2.7 2.7 0 0 1 5.1 1.1c0 1.9-2.7 2.2-2.7 3.8"></path>' +
            '<path d="M12 17.2h.01"></path>' +
            '</svg>';
        fmt.appendChild(btn);
        toolbar.appendChild(fmt);

        var root = document.createElement('div');
        root.className = CLS_ROOT;
        root.setAttribute('hidden', '');
        root.setAttribute('role', 'presentation');
        root.innerHTML =
            '<button type="button" class="hg-help-modal__backdrop" aria-label="Закрыть справку"></button>' +
            '<div class="hg-help-modal__panel" role="dialog" aria-modal="true" aria-labelledby="hg-help-modal-title">' +
            '<div class="hg-help-modal__head">' +
            '<div class="hg-help-modal__head-text">' +
            '<h2 id="hg-help-modal-title" class="hg-help-modal__title">Справка по кнопкам</h2>' +
            '<p class="hg-help-modal__lede">Те же значки, что в панели — кратко, что делает каждый.</p>' +
            '</div>' +
            '<button type="button" class="hg-help-modal__x" aria-label="Закрыть">' +
            '<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true">' +
            '<path d="M18 6L6 18M6 6l12 12"/>' +
            '</svg>' +
            '</button>' +
            '</div>' +
            '<div class="hg-help-modal__scroll">' +
            '<div class="hg-help-modal__list" role="list"></div>' +
            '</div>' +
            '<div class="hg-help-modal__foot">' +
            '<button type="button" class="hg-help-modal__btn-close">Закрыть</button>' +
            '</div>' +
            '</div>';

        var backdrop = root.querySelector('.hg-help-modal__backdrop');
        var listEl = root.querySelector('.hg-help-modal__list');
        var btnCloseFoot = root.querySelector('.hg-help-modal__btn-close');
        var btnCloseX = root.querySelector('.hg-help-modal__x');

        var portalMounted = false;

        function ensurePortal() {
            if (portalMounted) return;
            portalMounted = true;
            document.body.appendChild(root);
        }

        function helpKeyForControl(el) {
            if (!el) return '';
            if (el.classList && el.classList.contains('ql-picker-label') && el.parentElement) {
                el = el.parentElement;
            }
            var c = el.classList;
            if (!c) return '';
            if (c.contains('ql-font')) return 'font';
            if (c.contains('ql-header')) return 'header';
            if (c.contains('ql-align')) return 'align';
            if (c.contains('ql-color')) return 'color';
            if (c.contains('ql-background')) return 'background';
            if (c.contains('ql-list')) return 'list';
            if (c.contains('ql-bold')) return 'bold';
            if (c.contains('ql-italic')) return 'italic';
            if (c.contains('ql-underline')) return 'underline';
            if (c.contains('ql-link')) return 'link';
            if (c.contains('ql-image')) return 'image';
            if (c.contains('ql-clean')) return 'clean';
            if (c.contains('ql-post-bg-picker')) return 'post-bg';
            return '';
        }

        function stripPickerDropdown(pickerRoot) {
            if (!pickerRoot) return;
            Array.prototype.forEach.call(pickerRoot.querySelectorAll('.ql-picker-options'), function (node) {
                if (node && node.parentNode) node.parentNode.removeChild(node);
            });
            pickerRoot.classList.remove('ql-expanded');
            pickerRoot.removeAttribute('aria-expanded');
        }

        function neuterToolbarClone(rootEl) {
            if (!rootEl) return;
            rootEl.style.pointerEvents = 'none';
            var btns = Array.prototype.slice.call(rootEl.querySelectorAll('button'));
            if (rootEl.tagName === 'BUTTON' && btns.indexOf(rootEl) === -1) {
                btns.unshift(rootEl);
            }
            Array.prototype.forEach.call(btns, function (b) {
                b.type = 'button';
                b.disabled = true;
                b.setAttribute('tabindex', '-1');
                b.classList && b.classList.remove('ql-active');
                b.removeAttribute('aria-expanded');
                b.removeAttribute('aria-controls');
                b.removeAttribute('aria-pressed');
            });
            Array.prototype.forEach.call(rootEl.querySelectorAll('.ql-picker-label'), function (lab) {
                lab.setAttribute('tabindex', '-1');
                lab.classList && lab.classList.remove('ql-active', 'ql-expanded');
                lab.removeAttribute('aria-expanded');
                lab.removeAttribute('aria-controls');
            });
            Array.prototype.forEach.call(rootEl.querySelectorAll('.ql-picker'), function (pk) {
                pk.classList && pk.classList.remove('ql-expanded');
                pk.removeAttribute('aria-expanded');
            });
        }

        function buildCloneFromToolbarControl(original) {
            var cloneRoot;
            if (original.classList && original.classList.contains('ql-picker-label')) {
                var picker = original.closest && original.closest('.ql-picker');
                if (picker) {
                    cloneRoot = picker.cloneNode(true);
                    stripPickerDropdown(cloneRoot);
                } else {
                    cloneRoot = original.cloneNode(true);
                }
            } else {
                cloneRoot = original.cloneNode(true);
            }
            neuterToolbarClone(cloneRoot);
            return cloneRoot;
        }

        function helpTextForControl(el) {
            var key = helpKeyForControl(el);
            var map = {
                font: 'Шрифт. Меняет начертание текста (sans, serif, monospace и др.).',
                header: 'Заголовок. Делает строку заголовком и меняет размер (уровни 1–5).',
                align: 'Выравнивание. Сдвигает текст в абзаце влево, по центру, вправо или по ширине.',
                list: 'Список. Включает или выключает маркированный список.',
                bold: 'Жирный. Делает выделенный текст полужирным.',
                italic: 'Курсив. Наклоняет выделенный текст.',
                underline: 'Подчёркивание. Рисует линию под выделенным текстом.',
                image: 'Фото. Загружает картинку с устройства и вставляет её в текст.',
                link: 'Ссылка. После выделения текста открывает ввод адреса ссылки.',
                color: 'Цвет текста. Меняет цвет букв у выделенного фрагмента.',
                background: 'Фон строки. Подсветка за текстом, как маркер.',
                'post-bg': 'Фон открытки. Цвет или картинка на весь лист за текстом.',
                clean: 'Очистка. Снимает оформление с выделения (жирный, курсив, цвет и т.д.).'
            };
            if (map[key]) return map[key];
            var aria = el.getAttribute && (el.getAttribute('aria-label') || el.getAttribute('title'));
            if (aria) return String(aria);
            return 'Инструмент оформления текста.';
        }

        /** «Название. Описание» из одной строки справки — для двухстрочной карточки. */
        function splitHelpLine(text) {
            text = String(text || '').trim();
            if (!text) return { title: '', body: '' };
            var cut = text.indexOf('. ');
            if (cut !== -1) {
                return { title: text.slice(0, cut + 1).trim(), body: text.slice(cut + 2).trim() };
            }
            var cut2 = text.indexOf('.', 1);
            if (cut2 !== -1 && cut2 < text.length - 1) {
                return { title: text.slice(0, cut2 + 1).trim(), body: text.slice(cut2 + 1).replace(/^\s+/, '') };
            }
            return { title: text, body: '' };
        }

        function buildHelpList() {
            if (!listEl) return;
            listEl.innerHTML = '';

            var toolsRoot = toolbar.querySelector('.ql-toolbar-tools') || toolbar;
            var selector = [
                ':scope > button',
                ':scope .ql-post-bg-picker',
                ':scope .ql-picker > .ql-picker-label'
            ].join(', ');

            var controls = [];
            Array.prototype.forEach.call(toolsRoot.querySelectorAll(selector), function (el) {
                if (!el) return;
                if (btn.contains(el) || el === btn) return;
                if (el.classList && (el.classList.contains('editor-submit-btn') || el.classList.contains('hg-help-modal__btn-close'))) return;
                if (el.closest && el.closest('.' + CLS_ROOT)) return;
                if (el.classList && el.classList.contains('ql-post-help')) return;
                controls.push(el);
            });

            var uniq = [];
            controls.forEach(function (el) {
                if (uniq.indexOf(el) === -1) uniq.push(el);
            });
            controls = uniq;

            controls.forEach(function (original) {
                var row = document.createElement('div');
                row.className = 'hg-help-modal__row hg-help-modal__card';
                row.setAttribute('role', 'listitem');

                var swatch = document.createElement('div');
                swatch.className = 'hg-help-modal__swatch';

                var clone = buildCloneFromToolbarControl(original);
                clone.classList.add('hg-help-modal__icon-control');
                swatch.appendChild(clone);

                var textCol = document.createElement('div');
                textCol.className = 'hg-help-modal__text';
                var parts = splitHelpLine(helpTextForControl(original));
                var titleEl = document.createElement('div');
                titleEl.className = 'hg-help-modal__card-title';
                titleEl.textContent = parts.title;
                textCol.appendChild(titleEl);
                if (parts.body) {
                    var desc = document.createElement('p');
                    desc.className = 'hg-help-modal__card-desc';
                    desc.textContent = parts.body;
                    textCol.appendChild(desc);
                }

                row.appendChild(swatch);
                row.appendChild(textCol);
                listEl.appendChild(row);
            });
        }

        var isOpen = false;

        function open() {
            ensurePortal();
            buildHelpList();
            root.removeAttribute('hidden');
            isOpen = true;
            btn.classList.add('ql-active');
            btn.setAttribute('aria-expanded', 'true');
            document.documentElement.classList.add(CLS_OPEN);
            document.body.classList.add(CLS_OPEN);
        }

        function close() {
            if (!isOpen && root.hasAttribute('hidden')) return;
            root.setAttribute('hidden', '');
            isOpen = false;
            btn.classList.remove('ql-active');
            btn.setAttribute('aria-expanded', 'false');
            document.documentElement.classList.remove(CLS_OPEN);
            document.body.classList.remove(CLS_OPEN);
            try {
                btn.focus();
            } catch (_f) {}
        }

        function toggle(e) {
            if (e) e.preventDefault();
            if (root.hasAttribute('hidden')) open();
            else close();
        }

        btn.addEventListener('click', toggle);

        if (btnCloseFoot) btnCloseFoot.addEventListener('click', close);
        if (btnCloseX) btnCloseX.addEventListener('click', close);

        if (backdrop) {
            backdrop.addEventListener('click', function (e) {
                e.preventDefault();
                close();
            });
        }

        document.addEventListener('keydown', function onDocKey(e) {
            if (e.key !== 'Escape') return;
            if (root.hasAttribute('hidden')) return;
            close();
        });

    }

    global.HexgraphEditorHelp = {
        mount: mount
    };
})(typeof window !== 'undefined' ? window : this);
