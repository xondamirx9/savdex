<?php

declare(strict_types=1);

/*
 * Мини-сайты компаний: savdex.uz/s/acme, позже — acme.savdex.site.
 *
 * Для поддоменов — отдельный домен, а не поддомены savdex.uz. Страницы
 * оформляют сами компании, и держать их рядом с сессией площадки
 * нельзя: куки savdex.uz на savdex.site браузер не отправит вовсе,
 * а фишинговая страница «от имени SAVDEX» на чужом домене выглядит
 * чужой. Так же устроены github.io и vercel.app.
 */
return [
    /*
     * Хост мини-сайтов без поддомена, например savdex.site.
     *
     * Пусто — сайты живут на самой площадке: savdex.uz/s/acme. Так
     * запускаемся, пока свой домен не куплен. Когда появится, достаточно
     * задать MICROSITE_DOMAIN: адреса станут acme.savdex.site, а старые
     * ссылки вида /s/acme начнут вести туда постоянным перенаправлением.
     *
     * Локально для поддоменов — site.localhost: Chrome сам разрешает
     * acme.site.localhost. Просто localhost не годится: площадка на нём
     * же и закрылась бы RestrictSiteHost вместе с доменом мини-сайтов.
     */
    'domain' => env('MICROSITE_DOMAIN'),

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
