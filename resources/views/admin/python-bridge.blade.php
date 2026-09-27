{{--
    Переход в раздел админки на Django: форма сама отправляет пропуск.

    POST, а не ссылка с пропуском в адресе — адреса оседают в журналах
    сервера и в истории браузера. Кнопка — на случай выключенного
    JavaScript.
--}}
<!doctype html>
<html lang="ru">
<head>
    <meta charset="utf-8">
    <meta name="robots" content="noindex">
    <title>Переход…</title>
</head>
<body style="font-family: system-ui, sans-serif; padding: 2rem;">
    <form id="bridge" method="post" action="{{ $action }}">
        <input type="hidden" name="token" value="{{ $token }}">
        <p>Переходим в раздел админки…</p>
        <button type="submit">Продолжить</button>
    </form>
    <script>document.getElementById('bridge').submit();</script>
</body>
</html>
