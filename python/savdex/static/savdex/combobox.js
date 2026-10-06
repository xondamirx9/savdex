/*
 * Поиск в длинных выпадающих списках админки (компания, контакт, счёт…).
 *
 * Обычный <select> на сотни компаний открывался простынёй, в которой
 * не найти нужную. Здесь он превращается в поле с поиском:
 * - нажали на поле — печатаете часть названия, список показывает
 *   подходящие (регистр, «ё/е» и кавычки не важны);
 * - стрелка справа — весь список, как раньше;
 * - ↑/↓ и Enter — выбор с клавиатуры, Esc — отмена.
 *
 * Сам <select> остаётся в форме (скрытым) и отправляется как прежде:
 * сервер ничего нового не получает. Короткие списки (меньше MIN_OPTIONS),
 * множественный выбор, фильтры и доска CRM не трогаются; отдельный
 * список можно оставить обычным атрибутом data-plain.
 */
(function () {
    'use strict';

    var MIN_OPTIONS = 12;
    var SHOW = 100;
    var counter = 0;

    function norm(text) {
        return (text || '')
            .toLocaleLowerCase('ru')
            .replace(/ё/g, 'е')
            .replace(/[«»"'`„“”]/g, '')
            .replace(/\s+/g, ' ')
            .trim();
    }

    function skip(select) {
        return select.multiple
            || select.hasAttribute('data-plain')
            || select.dataset.sxCombo
            || select.options.length < MIN_OPTIONS
            || select.closest('.sx-board, #changelist-filter, .actions, [data-plain]');
    }

    function enhance(select) {
        if (skip(select)) return;

        select.dataset.sxCombo = '1';
        counter += 1;

        var items = Array.prototype.map.call(select.options, function (option) {
            return {
                value: option.value,
                label: option.text,
                key: norm(option.text),
                disabled: option.disabled,
            };
        });

        var wrap = document.createElement('div');
        wrap.className = 'sx-combo';

        var input = document.createElement('input');
        input.type = 'text';
        input.className = 'sx-combo-input';
        input.autocomplete = 'off';
        input.spellcheck = false;
        input.placeholder = 'Начните вводить или откройте список';
        input.setAttribute('role', 'combobox');
        input.setAttribute('aria-autocomplete', 'list');
        input.setAttribute('aria-expanded', 'false');

        var listId = 'sx-combo-list-' + counter;
        input.setAttribute('aria-controls', listId);

        // Подпись поля теперь ведёт в поле поиска
        if (select.id) {
            input.id = select.id + '_search';
            document.querySelectorAll('label[for="' + select.id + '"]').forEach(function (label) {
                label.htmlFor = input.id;
            });
        }

        // Обязательность переносится на видимое поле: скрытый обязательный
        // <select> браузер не может подсветить и молча не отправляет форму
        if (select.required) {
            input.required = true;
            select.required = false;
        }

        var toggle = document.createElement('button');
        toggle.type = 'button';
        toggle.className = 'sx-combo-toggle';
        toggle.tabIndex = -1;
        toggle.setAttribute('aria-label', 'Показать весь список');
        toggle.innerHTML = '<svg viewBox="0 0 20 20" aria-hidden="true"><path d="M5.5 7.5 10 12l4.5-4.5" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"/></svg>';

        var list = document.createElement('ul');
        list.className = 'sx-combo-list';
        list.id = listId;
        list.setAttribute('role', 'listbox');
        list.hidden = true;

        select.classList.add('sx-combo-native');
        select.tabIndex = -1;
        select.setAttribute('aria-hidden', 'true');
        select.parentNode.insertBefore(wrap, select.nextSibling);
        wrap.appendChild(input);
        wrap.appendChild(toggle);
        wrap.appendChild(list);

        var shown = [];
        var active = -1;

        function current() {
            var option = select.options[select.selectedIndex];

            return option && option.value !== '' ? option : null;
        }

        function showLabel() {
            var option = current();
            input.value = option ? option.text : '';
        }

        function isOpen() {
            return !list.hidden;
        }

        function close() {
            list.hidden = true;
            input.setAttribute('aria-expanded', 'false');
            input.removeAttribute('aria-activedescendant');
            active = -1;
        }

        function highlight(index) {
            var rows = list.querySelectorAll('.sx-combo-option');

            rows.forEach(function (row) {
                row.classList.remove('is-active');
                row.setAttribute('aria-selected', 'false');
            });

            active = index;

            if (index < 0 || !rows[index]) {
                input.removeAttribute('aria-activedescendant');
                return;
            }

            rows[index].classList.add('is-active');
            rows[index].setAttribute('aria-selected', 'true');
            input.setAttribute('aria-activedescendant', rows[index].id);
            rows[index].scrollIntoView({ block: 'nearest' });
        }

        function render(query, all) {
            var words = all ? [] : norm(query).split(' ').filter(Boolean);
            var found = items.filter(function (item) {
                if (item.value === '' && words.length) return false;

                return words.every(function (word) {
                    return item.key.indexOf(word) !== -1;
                });
            });

            // Начинается с запроса — выше, чем просто содержит его
            if (words.length) {
                found.sort(function (a, b) {
                    return (b.key.indexOf(words[0]) === 0) - (a.key.indexOf(words[0]) === 0);
                });
            }

            shown = found.slice(0, SHOW);
            list.innerHTML = '';

            shown.forEach(function (item, index) {
                var row = document.createElement('li');
                row.className = 'sx-combo-option';
                row.id = listId + '-' + index;
                row.setAttribute('role', 'option');
                row.textContent = item.value === '' ? '— не выбрано —' : item.label;

                if (item.value === select.value) row.classList.add('is-selected');
                if (item.disabled) row.setAttribute('aria-disabled', 'true');

                row.addEventListener('mousedown', function (event) {
                    // Иначе поле потеряет фокус раньше, чем сработает выбор
                    event.preventDefault();
                    choose(item);
                });
                list.appendChild(row);
            });

            if (!found.length) {
                var empty = document.createElement('li');
                empty.className = 'sx-combo-note';
                empty.textContent = 'Ничего не найдено';
                list.appendChild(empty);
            } else if (found.length > SHOW) {
                var more = document.createElement('li');
                more.className = 'sx-combo-note';
                more.textContent = 'Показаны первые ' + SHOW + ' из ' + found.length + ' — уточните поиск';
                list.appendChild(more);
            }

            list.hidden = false;
            input.setAttribute('aria-expanded', 'true');

            var selected = all ? shown.findIndex(function (item) { return item.value === select.value; }) : -1;
            highlight(selected >= 0 ? selected : (words.length && shown.length ? 0 : -1));
        }

        function choose(item) {
            if (!item || item.disabled) return;

            if (select.value !== item.value) {
                select.value = item.value;
                select.dispatchEvent(new Event('change', { bubbles: true }));
            }

            showLabel();
            close();
        }

        // Ушли из поля: введённое без выбора не оставляем — показываем
        // то, что на самом деле выбрано. Стёрли всё — выбор снимается
        function settle() {
            close();

            if (input.value.trim() === '' && items.some(function (item) { return item.value === ''; })) {
                choose(items.find(function (item) { return item.value === ''; }));
                return;
            }

            showLabel();
        }

        // Нажали на поле с выбранным названием — оно выделяется целиком,
        // и новый поиск печатается поверх, а не дописывается к названию
        function selectLabel() {
            var option = current();

            if (!option || input.value === option.text) input.select();
        }

        input.addEventListener('focus', selectLabel);
        input.addEventListener('click', selectLabel);

        input.addEventListener('input', function () {
            if (input.value.trim() === '') {
                close();
                return;
            }

            render(input.value, false);
        });

        input.addEventListener('blur', settle);

        input.addEventListener('keydown', function (event) {
            if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
                event.preventDefault();

                if (!isOpen()) {
                    var label = current() ? current().text : '';
                    render(input.value, input.value === label || input.value === '');
                    return;
                }

                var step = event.key === 'ArrowDown' ? 1 : -1;
                var next = Math.max(0, Math.min(shown.length - 1, active + step));
                highlight(next);
            } else if (event.key === 'Enter') {
                if (isOpen()) {
                    // Enter выбирает, а не отправляет форму
                    event.preventDefault();

                    if (active >= 0) choose(shown[active]);
                    else if (shown.length === 1) choose(shown[0]);
                }
            } else if (event.key === 'Escape') {
                if (isOpen()) {
                    event.preventDefault();
                    close();
                    showLabel();
                }
            }
        });

        toggle.addEventListener('mousedown', function (event) {
            event.preventDefault();
        });

        toggle.addEventListener('click', function () {
            if (isOpen()) {
                close();
                return;
            }

            if (document.activeElement !== input) input.focus();
            render('', true);
        });

        select.addEventListener('change', showLabel);
        showLabel();
    }

    function enhanceAll(root) {
        (root || document).querySelectorAll('#content select').forEach(enhance);
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', function () { enhanceAll(); });
    } else {
        enhanceAll();
    }

    // Новые строки во вложенных формах Django
    document.addEventListener('formset:added', function (event) {
        event.target.querySelectorAll('select').forEach(enhance);
    });
})();
