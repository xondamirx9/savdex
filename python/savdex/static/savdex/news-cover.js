/*
 * «Загрузить фото» обложки новости — с редактором.
 *
 * Выбранное фото открывается в рамке того же формата, что обложка на
 * сайте (16:10): его можно двигать, приближать и поворачивать. В поле
 * формы уходит уже обрезанный снимок рамки — в ленте новостей окажется
 * ровно то, что видно в редакторе. Без JavaScript остаётся обычное
 * поле выбора файла: сервер принимает и необрезанное фото.
 */
(function () {
    'use strict';

    var input = document.querySelector('input[name="cover_upload"]');
    if (!input || !window.DataTransfer) return;

    var RATIO = 16 / 10;
    var OUT_W = 1920;
    var MAX_ZOOM = 4;

    var current = document.getElementById('news-cover-current');

    // ── Кнопка и превью вместо голого поля файла ──
    var box = document.createElement('div');
    box.className = 'news-cover-box';
    var preview = document.createElement('div');
    preview.className = 'news-cover-preview';
    var button = document.createElement('button');
    button.type = 'button';
    button.className = 'button news-cover-button';
    var note = document.createElement('span');
    note.className = 'news-cover-note';

    function showPreview(src) {
        preview.innerHTML = '';
        if (src) {
            var img = document.createElement('img');
            img.src = src;
            img.alt = '';
            preview.appendChild(img);
            preview.classList.remove('is-empty');
        } else {
            preview.textContent = 'Фото нет — на сайте будет градиент по рубрике';
            preview.classList.add('is-empty');
        }
        button.textContent = src ? 'Заменить фото' : 'Загрузить фото';
    }

    showPreview(current ? current.getAttribute('data-src') : '');
    input.classList.add('news-cover-native');
    input.parentNode.insertBefore(box, input);
    box.appendChild(preview);
    box.appendChild(button);
    box.appendChild(note);
    box.appendChild(input);

    button.addEventListener('click', function () { input.click(); });

    input.addEventListener('change', function () {
        var file = input.files && input.files[0];
        if (!file || input.dataset.cropped === '1') {
            input.dataset.cropped = '';
            return;
        }
        open(file);
    });

    // ── Редактор ──
    function open(file) {
        var url = URL.createObjectURL(file);
        var image = new Image();
        var state = { zoom: 1, rotation: 0, x: 0, y: 0 };

        var overlay = el('div', 'news-cover-overlay');
        var dialog = el('div', 'news-cover-dialog');
        dialog.setAttribute('role', 'dialog');
        dialog.setAttribute('aria-modal', 'true');
        dialog.setAttribute('aria-label', 'Редактор фото');
        var title = el('h2', 'news-cover-title', 'Редактор фото');
        var hint = el('p', 'news-cover-hint', 'Перетащите фото и подберите масштаб — в рамку попадёт то, что будет на обложке новости.');
        var frame = el('div', 'news-cover-frame');
        var img = el('img');
        img.alt = '';
        img.draggable = false;
        frame.appendChild(img);

        var controls = el('div', 'news-cover-controls');
        var zoomLabel = el('label', 'news-cover-zoom', 'Масштаб ');
        var zoom = document.createElement('input');
        zoom.type = 'range';
        zoom.min = '1';
        zoom.max = String(MAX_ZOOM);
        zoom.step = '0.01';
        zoom.value = '1';
        zoomLabel.appendChild(zoom);
        var rotate = el('button', 'button', 'Повернуть ↻');
        rotate.type = 'button';
        controls.appendChild(zoomLabel);
        controls.appendChild(rotate);

        var actions = el('div', 'news-cover-actions');
        var cancel = el('button', 'button', 'Отмена');
        cancel.type = 'button';
        var apply = el('button', 'button default', 'Применить');
        apply.type = 'button';
        actions.appendChild(cancel);
        actions.appendChild(apply);

        [title, hint, frame, controls, actions].forEach(function (n) { dialog.appendChild(n); });
        overlay.appendChild(dialog);
        document.body.appendChild(overlay);

        function size() {
            var w = frame.clientWidth;
            return { w: w, h: w / RATIO };
        }

        function natural() {
            var turned = state.rotation % 180 !== 0;
            return {
                w: turned ? image.naturalHeight : image.naturalWidth,
                h: turned ? image.naturalWidth : image.naturalHeight
            };
        }

        function scale() {
            var f = size();
            var n = natural();
            return Math.max(f.w / n.w, f.h / n.h) * state.zoom;
        }

        // Фото всегда закрывает рамку: сдвиг не даёт отойти от края
        function clamp() {
            var f = size();
            var n = natural();
            var s = scale();
            var maxX = Math.max(0, (n.w * s - f.w) / 2);
            var maxY = Math.max(0, (n.h * s - f.h) / 2);
            state.x = Math.min(maxX, Math.max(-maxX, state.x));
            state.y = Math.min(maxY, Math.max(-maxY, state.y));
        }

        function draw() {
            clamp();
            img.style.width = image.naturalWidth + 'px';
            img.style.height = image.naturalHeight + 'px';
            img.style.transform = 'translate(-50%, -50%) translate(' + state.x + 'px, ' + state.y + 'px) rotate(' +
                state.rotation + 'deg) scale(' + scale() + ')';
        }

        image.onload = function () {
            img.src = url;
            draw();
        };
        image.src = url;

        var drag = null;
        frame.addEventListener('pointerdown', function (e) {
            frame.setPointerCapture(e.pointerId);
            drag = { x: e.clientX, y: e.clientY, sx: state.x, sy: state.y };
        });
        frame.addEventListener('pointermove', function (e) {
            if (!drag) return;
            state.x = drag.sx + e.clientX - drag.x;
            state.y = drag.sy + e.clientY - drag.y;
            draw();
        });
        ['pointerup', 'pointercancel'].forEach(function (t) {
            frame.addEventListener(t, function () { drag = null; });
        });
        frame.addEventListener('wheel', function (e) {
            e.preventDefault();
            setZoom(state.zoom - e.deltaY * 0.002);
        }, { passive: false });

        function setZoom(value) {
            state.zoom = Math.min(MAX_ZOOM, Math.max(1, value));
            zoom.value = String(state.zoom);
            draw();
        }

        zoom.addEventListener('input', function () { setZoom(Number(zoom.value)); });
        rotate.addEventListener('click', function () {
            state.rotation = (state.rotation + 90) % 360;
            state.x = 0;
            state.y = 0;
            setZoom(1);
        });

        function close() {
            URL.revokeObjectURL(url);
            overlay.remove();
            document.removeEventListener('keydown', onKey);
        }

        function onKey(e) {
            if (e.key === 'Escape') {
                input.value = '';
                close();
            }
        }
        document.addEventListener('keydown', onKey);

        cancel.addEventListener('click', function () {
            input.value = '';
            close();
        });

        // Снимок рамки тем же преобразованием, что на экране, в полном размере
        apply.addEventListener('click', function () {
            var f = size();
            var k = OUT_W / f.w;
            var canvas = document.createElement('canvas');
            canvas.width = OUT_W;
            canvas.height = Math.round(OUT_W / RATIO);
            var ctx = canvas.getContext('2d');
            ctx.fillStyle = '#ffffff';
            ctx.fillRect(0, 0, canvas.width, canvas.height);
            ctx.imageSmoothingQuality = 'high';
            ctx.translate(canvas.width / 2 + state.x * k, canvas.height / 2 + state.y * k);
            ctx.rotate(state.rotation * Math.PI / 180);
            var s = scale() * k;
            ctx.scale(s, s);
            ctx.drawImage(image, -image.naturalWidth / 2, -image.naturalHeight / 2);

            canvas.toBlob(function (blob) {
                if (!blob) return;
                var name = (file.name.replace(/\.[^.]+$/, '') || 'cover') + '.jpg';
                var cropped = new File([blob], name, { type: 'image/jpeg' });
                var transfer = new DataTransfer();
                transfer.items.add(cropped);
                input.dataset.cropped = '1';
                input.files = transfer.files;
                input.dispatchEvent(new Event('change', { bubbles: true }));
                showPreview(URL.createObjectURL(cropped));
                note.textContent = 'Новое фото сохранится вместе с новостью';
                close();
            }, 'image/jpeg', 0.9);
        });
    }

    function el(tag, cls, text) {
        var n = document.createElement(tag);
        if (cls) n.className = cls;
        if (text) n.textContent = text;
        return n;
    }

})();
