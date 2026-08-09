# Личный кабинет, админка и служебные адреса закрыты: индексировать
# там нечего, а робот тратит на них лимит обхода, который лучше уходит
# на карточки объявлений и компаний.
User-agent: *
Disallow: /cabinet
Disallow: /admin
Disallow: /onboarding
Disallow: /notifications
Disallow: /login
Disallow: /register
Disallow: /forgot-password
Disallow: /reset-password
Disallow: /verify-email
Disallow: /password
Disallow: /files/

# Сортировка и постраничная навигация дают одно и то же содержимое
# под разными адресами. Карточки при этом остаются доступны — робот
# приходит на них по ссылкам из карты сайта.
# Параметр перечислен дважды: в адресе он бывает и первым, и после
# фильтра — «?sort=cheap» и «?category=3&sort=cheap», а правило
# сопоставляется с адресом посимвольно
Disallow: /*?sort=
Disallow: /*&sort=
Disallow: /*?page=
Disallow: /*&page=

Sitemap: {{ url('/sitemap.xml') }}
