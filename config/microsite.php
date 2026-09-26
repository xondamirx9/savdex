<?php

declare(strict_types=1);

/*
 * Мини-сайты компаний: acme.savdex.site.
 *
 * Отдельный домен, а не поддомены savdex.uz, — сознательно. Страницы
 * оформляют сами компании, и держать их рядом с сессией площадки
 * нельзя: куки savdex.uz на savdex.site браузер не отправит вовсе,
 * а фишинговая страница «от имени SAVDEX» на чужом домене выглядит
 * чужой. Так же устроены github.io и vercel.app.
 */
return [
    // Хост без поддомена. Локально — site.localhost: Chrome сам
    // разрешает acme.site.localhost, запись в hosts не нужна. Просто
    // localhost не годится: площадка на нём же и закрылась бы
    // RestrictSiteHost вместе с доменом мини-сайтов
    'domain' => env('MICROSITE_DOMAIN', 'savdex.site'),

    /*
     * Адреса, которые компания занять не может: служебные имена,
     * которые понадобятся площадке, и те, что выглядят как её
     * собственные страницы, — support.savdex.site от компании
     * читался бы как поддержка SAVDEX.
     */
    'reserved' => [
        'www', 'api', 'app', 'admin', 'cabinet', 'mail', 'smtp', 'imap', 'pop', 'ftp',
        'ns1', 'ns2', 'cdn', 'static', 'assets', 'media', 'img', 'files',
        'help', 'support', 'status', 'blog', 'news', 'docs',
        'dev', 'test', 'staging', 'demo', 'beta',
        'savdex', 'official', 'pay', 'payment', 'billing', 'login', 'auth', 'account',
    ],
];
