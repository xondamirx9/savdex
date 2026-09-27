/*
 * Предпросмотр баннера в админке. Повторяет витрину (BannerSlot.tsx):
 * картинка обрезается object-fit: cover с object-position по точке
 * фокуса, на телефоне — своя картинка, если загружена, иначе широкая.
 * Всё обновляется до сохранения: выбранный файл читается в браузере.
 */
(function () {
    'use strict';

    var root = document.getElementById('banner-preview');
    var dataTag = document.getElementById('banner-preview-data');
    if (!root || !dataTag) return;

    var data = JSON.parse(dataTag.textContent);
    var el = function (role) { return root.querySelector('[data-role="' + role + '"]'); };
    var field = function (name) { return document.querySelector('[name="' + name + '"]'); };

    // Выбранные, но ещё не сохранённые файлы — поверх сохранённых
    var local = { image: null, mobile: null };
    var language = '';

    function focal() {
        var x = Math.min(100, Math.max(0, parseInt(field('focal_x').value, 10) || 0));
        var y = Math.min(100, Math.max(0, parseInt(field('focal_y').value, 10) || 0));
        return { x: x, y: y };
    }

    function pictures() {
        var base = { image: local.image || data.image, mobile: local.mobile || data.mobile };
        var own = language && data.languages[language];

        if (!own) return base;

        // Как mobileImageFor(): у языка без своей узкой картинки чужую
        // узкую не берём — на ней чужой текст; обрезается своя широкая
        return { image: own.image, mobile: own.mobile };
    }

    function render() {
        var p = pictures();
        var f = focal();
        var position = f.x + '% ' + f.y + '%';
        var has = Boolean(p.image);

        el('empty').style.display = has ? 'none' : '';
        root.querySelectorAll('.banner-preview__row').forEach(function (row) {
            row.style.display = has ? '' : 'none';
        });
        if (!has) return;

        var desktop = el('desktop');
        desktop.src = p.image;
        desktop.style.objectPosition = position;

        var mobile = el('mobile');
        mobile.src = p.mobile || p.image;
        mobile.style.objectPosition = position;
        el('mobile-note').textContent = p.mobile
            ? 'Своя картинка для телефона.'
            : 'Картинки для телефона нет — широкая обрезана по точке фокуса.';

        el('focus').src = p.image;
        el('dot').style.left = f.x + '%';
        el('dot').style.top = f.y + '%';

        var dismissible = field('is_dismissible');
        root.querySelectorAll('[data-role="close"]').forEach(function (x) {
            x.style.display = dismissible && dismissible.checked ? '' : 'none';
        });
    }

    function languages() {
        var box = el('languages');
        var codes = Object.keys(data.languages);
        box.innerHTML = '';
        if (codes.length === 0) return;

        [''].concat(codes).forEach(function (code) {
            var button = document.createElement('button');
            button.type = 'button';
            button.textContent = code ? data.languages[code].label : 'Основная';
            button.className = code === language ? 'is-active' : '';
            button.addEventListener('click', function () {
                language = code;
                languages();
                render();
            });
            box.appendChild(button);
        });
    }

    function readInto(input, key) {
        if (!input) return;
        input.addEventListener('change', function () {
            var file = input.files && input.files[0];
            if (!file) { local[key] = null; render(); return; }
            var reader = new FileReader();
            reader.onload = function () { local[key] = reader.result; language = ''; languages(); render(); };
            reader.readAsDataURL(file);
        });
    }

    readInto(field('image_upload'), 'image');
    readInto(field('image_mobile_upload'), 'mobile');
    ['focal_x', 'focal_y', 'is_dismissible'].forEach(function (name) {
        var input = field(name);
        if (input) { input.addEventListener('input', render); input.addEventListener('change', render); }
    });

    // Точка фокуса щелчком по картинке
    el('focus-box').addEventListener('click', function (event) {
        var box = el('focus').getBoundingClientRect();
        field('focal_x').value = Math.round(((event.clientX - box.left) / box.width) * 100);
        field('focal_y').value = Math.round(((event.clientY - box.top) / box.height) * 100);
        render();
    });

    languages();
    render();
})();
