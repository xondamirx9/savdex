<?php

declare(strict_types=1);

/*
|--------------------------------------------------------------------------
| Платёжные провайдеры
|--------------------------------------------------------------------------
|
| Каждый провайдер включается своим флагом enabled. Пока он false —
| онлайн-касса не работает, а оплата идёт по счёту с ручным
| подтверждением (как и было). Это значит, что незаполненные ключи
| ничего не ломают на проде: провайдер просто выключен.
|
| Точные имена полей и URL уточняются по документации провайдера
| (для Uzum — их merchant-кабинет и техдок), но структура конфигурации
| от этого не меняется.
|
*/

return [

    'default' => env('PAYMENTS_DEFAULT', 'uzum'),

    /*
     * Валюта площадки. Суммы в базе хранятся в сумах; провайдерам,
     * считающим в тийинах, отдаётся Payment::amountMinor().
     */
    'currency' => 'UZS',

    'providers' => [

        'uzum' => [
            'enabled' => (bool) env('PAYMENTS_UZUM_ENABLED', false),

            /*
             * Онлайн-касса на витрине — кнопка «Оплатить» с уводом на
             * платёжную страницу. Отдельный флаг, а не enabled: колбэки
             * Merchant API включаются раньше (их тестирует Uzum при
             * подключении), чем витрине есть куда уводить покупателя.
             */
            'checkout' => (bool) env('PAYMENTS_UZUM_CHECKOUT_ENABLED', false),

            /*
             * Basic auth входящих вызовов Merchant API (check, create,
             * confirm, reverse, status). Логин и пароль согласуются
             * с Uzum при подключении; пустые значения запирают
             * эндпойнты — без пароля не отвечает ни одна операция.
             */
            'callback_login' => env('PAYMENTS_UZUM_CALLBACK_LOGIN'),
            'callback_password' => env('PAYMENTS_UZUM_CALLBACK_PASSWORD'),

            // Имя поля в params, в котором Uzum передаёт номер счёта.
            // Задаётся в их merchant-кабинете — здесь то же значение
            'account_field' => env('PAYMENTS_UZUM_ACCOUNT_FIELD', 'invoice'),

            // Созданная, но не подтверждённая транзакция сгорает
            // через столько минут — по протоколу Merchant API
            'confirm_timeout_minutes' => (int) env('PAYMENTS_UZUM_CONFIRM_TIMEOUT', 30),

            // Боевой/тестовый контур переключается флагом sandbox —
            // на тесте бьём по sandbox-URL и тестовыми ключами.
            // base_url — адрес API Uzum Checkout (тестовый или боевой),
            // его выдаёт менеджер Uzum вместе с терминалом и ключом
            'sandbox' => (bool) env('PAYMENTS_UZUM_SANDBOX', true),
            'base_url' => env('PAYMENTS_UZUM_BASE_URL'),

            // Идентификаторы мерчанта из кабинета Uzum.
            // terminal_id уходит в заголовок X-Terminal-Id запросов
            // Checkout; service_id сверяется в колбэках Merchant API
            'merchant_id' => env('PAYMENTS_UZUM_MERCHANT_ID'),
            'service_id' => env('PAYMENTS_UZUM_SERVICE_ID'),
            'terminal_id' => env('PAYMENTS_UZUM_TERMINAL_ID'),

            // API-ключ Uzum Checkout — заголовок X-API-Key исходящих
            // запросов. В репозитории пусто — задаётся только в окружении
            'secret_key' => env('PAYMENTS_UZUM_SECRET_KEY'),
            'webhook_secret' => env('PAYMENTS_UZUM_WEBHOOK_SECRET'),

            // Куда провайдер возвращает покупателя после оплаты
            'return_url' => env('PAYMENTS_UZUM_RETURN_URL', env('APP_URL').'/cabinet/billing'),

            // Список IP колбэков Uzum, если провайдер их публикует —
            // дополнительная проверка сверх подписи. Пусто = не проверяем IP
            'callback_ips' => array_filter(explode(',', (string) env('PAYMENTS_UZUM_CALLBACK_IPS', ''))),
        ],

    ],

];
