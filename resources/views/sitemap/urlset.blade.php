<?php echo '<?xml version="1.0" encoding="UTF-8"?>'."\n"; ?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" xmlns:xhtml="http://www.w3.org/1999/xhtml">
@foreach ($urls as $url)
    <url>
        <loc>{{ $url['loc'] }}</loc>
@isset ($url['lastmod'])
        <lastmod>{{ $url['lastmod'] }}</lastmod>
@endisset
        <changefreq>{{ $url['changefreq'] }}</changefreq>
        <priority>{{ $url['priority'] }}</priority>
{{-- Языковые версии перечисляются у каждого адреса, включая его
     самого: односторонняя связка не засчитывается, и робот должен
     узнать обо всех переводах, зайдя на любой из них. --}}
@foreach ($url['alternates'] ?? [] as $hreflang => $href)
        <xhtml:link rel="alternate" hreflang="{{ $hreflang }}" href="{{ $href }}"/>
@endforeach
    </url>
@endforeach
</urlset>
