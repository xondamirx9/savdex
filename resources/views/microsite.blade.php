<!DOCTYPE html>
{{--
    Корневой шаблон мини-сайта. Отдельный от app.blade.php: вывеска
    здесь компании, а не площадки — её название во вкладке, её логотип
    иконкой и og:site_name, без знака SAVDEX.

    Переменные оформления печатает сервер, а не скрипт: иначе страница
    первые мгновения мигала бы цветами площадки. Строка siteCss собрана
    SiteTheme::css() только из проверенных значений.
--}}
<html lang="{{ str_replace('_', '-', app()->getLocale()) }}">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
    <meta name="csrf-token" content="{{ csrf_token() }}">

    @if ($siteIcon)
        <link rel="icon" href="{{ $siteIcon }}">
    @endif

    <title inertia>{{ $siteTitle }}</title>

    @if ($siteDescription !== '')
        <meta name="description" content="{{ $siteDescription }}">
        <meta property="og:description" content="{{ $siteDescription }}">
    @endif

    @if ($siteNoindex)
        <meta name="robots" content="noindex, nofollow">
    @else
        <link rel="canonical" href="{{ $siteCanonical }}">
    @endif

    <meta property="og:type" content="website">
    <meta property="og:site_name" content="{{ $siteTitle }}">
    <meta property="og:title" content="{{ $siteTitle }}">
    <meta property="og:url" content="{{ $siteCanonical }}">
    @if ($siteIcon)
        <meta property="og:image" content="{{ $siteIcon }}">
    @endif

    <style>:root{ {!! $siteCss !!} }</style>

    <link rel="preconnect" href="https://fonts.bunny.net">
    <link rel="preconnect" href="https://fonts.bunny.net" crossorigin>
    <link id="ms-fonts" href="{{ $siteFonts }}" rel="stylesheet">

    @viteReactRefresh
    @vite(['resources/css/app.css', 'resources/js/app.tsx'])
    @inertiaHead
</head>
<body class="antialiased ms-body">
    @inertia
</body>
</html>
