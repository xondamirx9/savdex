/*
 * Адрес новости из заголовка — пока его не правили руками.
 * Кириллица и узбекская латиница переводятся в латиницу, всё прочее —
 * дефис. Это подсказка: сервер всё равно проверяет адрес.
 */
(function () {
    'use strict';

    var title = document.querySelector('[name="title"]');
    var slug = document.querySelector('[name="slug"]');
    if (!title || !slug) return;

    var map = {
        а: 'a', б: 'b', в: 'v', г: 'g', д: 'd', е: 'e', ё: 'yo', ж: 'zh', з: 'z', и: 'i', й: 'y',
        к: 'k', л: 'l', м: 'm', н: 'n', о: 'o', п: 'p', р: 'r', с: 's', т: 't', у: 'u', ф: 'f',
        х: 'kh', ц: 'ts', ч: 'ch', ш: 'sh', щ: 'sch', ъ: '', ы: 'y', ь: '', э: 'e', ю: 'yu', я: 'ya',
        ў: 'o', қ: 'q', ғ: 'g', ҳ: 'h', 'ʻ': '', 'ʼ': '', "'": ''
    };
    var touched = slug.value !== '';

    slug.addEventListener('input', function () { touched = slug.value !== ''; });
    title.addEventListener('input', function () {
        if (touched) return;
        slug.value = title.value.toLowerCase().split('').map(function (ch) {
            return Object.prototype.hasOwnProperty.call(map, ch) ? map[ch] : ch;
        }).join('').replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 190);
    });
})();
