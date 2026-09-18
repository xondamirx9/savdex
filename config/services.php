<?php

return [

    /*
    |--------------------------------------------------------------------------
    | Third Party Services
    |--------------------------------------------------------------------------
    |
    | This file is for storing the credentials for third party services such
    | as Mailgun, Postmark, AWS and more. This file provides the de facto
    | location for this type of information, allowing packages to have
    | a conventional file to locate the various service credentials.
    |
    */

    'postmark' => [
        'key' => env('POSTMARK_API_KEY'),
    ],

    'resend' => [
        'key' => env('RESEND_API_KEY'),
    ],

    'ses' => [
        'key' => env('AWS_ACCESS_KEY_ID'),
        'secret' => env('AWS_SECRET_ACCESS_KEY'),
        'region' => env('AWS_DEFAULT_REGION', 'us-east-1'),
    ],

    'slack' => [
        'notifications' => [
            'bot_user_oauth_token' => env('SLACK_BOT_USER_OAUTH_TOKEN'),
            'channel' => env('SLACK_BOT_USER_DEFAULT_CHANNEL'),
        ],
    ],

    /*
     * Машинный перевод объявлений на языки каталога.
     * Выключается переменной, если сервис перевода недоступен.
     */
    'machine_translation' => [
        'enabled' => env('MACHINE_TRANSLATION_ENABLED', true),
    ],

    /*
     * Бот Telegram: им площадка присылает ссылку на смену пароля тем,
     * кто привязал Telegram к учётной записи. Заводится в @BotFather
     * за минуту; пока токена нет, способ не показывается на форме.
     *
     * webhook_secret — часть адреса, на который Telegram присылает
     * сообщения: адрес без секрета открыт всему интернету, и написать
     * в него «/start чужой-токен» мог бы кто угодно.
     */
    'telegram' => [
        'bot_token' => env('TELEGRAM_BOT_TOKEN'),
        'bot_username' => env('TELEGRAM_BOT_USERNAME'),
        'webhook_secret' => env('TELEGRAM_WEBHOOK_SECRET'),
    ],

    /*
     * WhatsApp Business (Meta Cloud API). Сообщение вне суточного окна
     * переписки отправляется только утверждённым шаблоном — его имя
     * задаётся здесь же. Шаблон нужен категории «Аутентификация»
     * с одной переменной: в неё подставляется ссылка.
     */
    'whatsapp' => [
        'token' => env('WHATSAPP_TOKEN'),
        'phone_number_id' => env('WHATSAPP_PHONE_NUMBER_ID'),
        'template' => env('WHATSAPP_TEMPLATE', 'password_reset'),
        'api_version' => env('WHATSAPP_API_VERSION', 'v21.0'),
    ],

];
