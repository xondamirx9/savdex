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

            // Боевой/тестовый контур переключается флагом sandbox —
            // на тесте бьём по sandbox-URL и тестовыми ключами
            'sandbox' => (bool) env('PAYMENTS_UZUM_SANDBOX', true),
            'base_url' => env('PAYMENTS_UZUM_BASE_URL'),

            // Идентификаторы мерчанта из кабинета Uzum
            'merchant_id' => env('PAYMENTS_UZUM_MERCHANT_ID'),
            'service_id' => env('PAYMENTS_UZUM_SERVICE_ID'),
            'terminal_id' => env('PAYMENTS_UZUM_TERMINAL_ID'),

            // Секрет для подписи исходящих запросов и проверки колбэков.
            // В репозитории пусто — задаётся только в окружении сервера
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
