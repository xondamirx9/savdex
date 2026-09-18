@php($seo = app(App\Support\Seo::class))
<!DOCTYPE html>
<html lang="{{ str_replace('_', '-', app()->getLocale()) }}">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
    <meta name="csrf-token" content="{{ csrf_token() }}">

    {{--
        Знак площадки: загруженный в админке логотип, ico — запасной.

        type проставляется только вектору: браузер выбирает иконку
        по нему, не скачивая файл, и с чужим типом вкладка остаётся
        с пустым листом.
    --}}
    @php($logo = App\Support\Appearance::logo())
    <link rel="icon" href="/favicon.ico" sizes="32x32">
    <link rel="icon" @if ($type = App\Support\Appearance::logoType()) type="{{ $type }}" @endif href="{{ $logo }}">
    <link rel="apple-touch-icon" href="{{ App\Support\Appearance::touchIcon() }}">

    {{--
        Мета-теги печатает сервер, а не скрипт.

        Inertia проставляет их уже в браузере — этого хватает человеку,
        но не роботу: превью-боты Telegram и WhatsApp не выполняют
        JavaScript вообще, а Яндекс отрисовывает его неохотно. Ссылка
        на объявление, отправленная в Telegram, выглядела голым адресом.

        @inertiaHead ниже добавляет клиентские теги при переходах без
        перезагрузки — заголовок вкладки должен меняться и там.
    --}}
    <title inertia>{{ $seo->getTitle() }}</title>

    @if ($seo->getDescription() !== '')
        <meta name="description" content="{{ $seo->getDescription() }}">
    @endif

    {{-- Служебные страницы (404 и прочие ошибки) canonical и hreflang
         не печатают: канонический адрес несуществующей страницы —
         приглашение её индексировать --}}
    @unless ($seo->isBare())
        <link rel="canonical" href="{{ $seo->getCanonical() }}">

        {{-- Языковые версии страницы. Указываются на каждой из них и
             обязательно включают саму себя — иначе поисковик считает
             связку односторонней и игнорирует её целиком. --}}
        @foreach ($seo->getAlternates() as $hreflang => $href)
            <link rel="alternate" hreflang="{{ $hreflang }}" href="{{ $href }}">
        @endforeach
    @endunless

    @if ($seo->isNoindex())
        {{-- follow оставляем: страница не нужна в индексе, но ссылки
             с неё ведут на карточки, которые нужны --}}
        <meta name="robots" content="noindex, follow">
    @endif

    <meta property="og:type" content="{{ $seo->getType() }}">
    <meta property="og:site_name" content="SAVDEX">
    <meta property="og:locale" content="{{ str_replace('-', '_', app()->getLocale()) }}">
    <meta property="og:title" content="{{ $seo->getTitle() }}">
    <meta property="og:url" content="{{ $seo->getCanonical() }}">
    @if ($seo->getDescription() !== '')
        <meta property="og:description" content="{{ $seo->getDescription() }}">
    @endif
    {{-- Картинка есть всегда: при её отсутствии Seo подставляет
         фирменную заглушку, иначе ссылка в Telegram выглядит узкой
         строчкой, которую в переписке не замечают --}}
    <meta property="og:image" content="{{ $seo->getImage() }}">
    @if ($meta = $seo->getImageMeta())
        <meta property="og:image:width" content="{{ $meta['width'] }}">
        <meta property="og:image:height" content="{{ $meta['height'] }}">
        <meta property="og:image:type" content="{{ $meta['type'] }}">
    @endif
    <meta name="twitter:card" content="summary_large_image">
    <meta name="twitter:title" content="{{ $seo->getTitle() }}">
    @if ($seo->getDescription() !== '')
        <meta name="twitter:description" content="{{ $seo->getDescription() }}">
    @endif
    <meta name="twitter:image" content="{{ $seo->getImage() }}">

    @if ($json = $seo->getJsonLd())
        <script type="application/ld+json">{!! $json !!}</script>
    @endif

    {{--
        Manrope со стороннего домена. Локальный был бы быстрее —
        внешний запрос откладывает отрисовку текста и ставит скорость
        площадки в зависимость от чужого сервера, а из Узбекистана
        европейские CDN отвечают заметно медленнее. Пока шрифт внешний,
        второй preconnect с crossorigin обязателен: без него браузер
        открывает соединение только под стили, а под сами woff2 —
        заново, и это лишний круг до первой отрисовки текста.

        Пять начертаний — ровно те, которыми набрана вёрстка. Просить
        то, чего у семейства нет, нельзя: ответ на такой запрос ломает
        весь список, и страница осталась бы вообще без шрифта.
    --}}
    <link rel="preconnect" href="https://fonts.bunny.net">
    <link rel="preconnect" href="https://fonts.bunny.net" crossorigin>
    <link href="https://fonts.bunny.net/css?family=manrope:400,500,600,700,800&display=swap" rel="stylesheet">

    @viteReactRefresh
    @vite(['resources/css/app.css', 'resources/js/app.tsx'])
    @inertiaHead
</head>
<body class="antialiased">
    @inertia
</body>
</html>
