<?php

declare(strict_types=1);

namespace App\Console\Commands;

use App\Services\Messaging\TelegramGateway;
use Illuminate\Console\Command;

/**
 * Регистрация бота у Telegram одной командой.
 *
 * Раньше адрес приходилось собирать руками и вставлять в него токен
 * с секретом. Это ровно тот случай, когда в строку уезжает «<ТОКЕН>»
 * как есть, Telegram отвечает «Not Found», и человек ищет ошибку
 * в сайте, которого она не касается.
 *
 * Здесь токен и секрет берутся из переменных окружения, адрес
 * собирается из APP_URL, а ответ Telegram пересказывается по-русски.
 */
class TelegramWebhook extends Command
{
    protected $signature = 'telegram:webhook
        {--info : Показать, что Telegram знает о боте сейчас}
        {--delete : Снять адрес, бот перестанет получать сообщения}';

    protected $description = 'Сообщить Telegram адрес, на который присылать сообщения боту';

    public function handle(TelegramGateway $telegram): int
    {
        if (! $telegram->configured()) {
            $this->components->error('Бот не настроен.');
            $this->line('  Задайте TELEGRAM_BOT_TOKEN (выдаёт @BotFather) и TELEGRAM_BOT_USERNAME (имя бота без «@»).');

            return self::FAILURE;
        }

        if ($this->option('delete')) {
            return $this->report($telegram->deleteWebhook(), 'Адрес снят: бот больше не получает сообщения.');
        }

        if ($this->option('info')) {
            return $this->info_($telegram);
        }

        if ($telegram->webhookSecret() === '') {
            $this->components->error('Не задан TELEGRAM_WEBHOOK_SECRET.');
            $this->line('  Это любая случайная строка из 8–64 знаков (латиница, цифры, «-», «_»).');
            $this->line('  Она становится частью адреса — без неё писать боту от чужого имени мог бы кто угодно.');

            return self::FAILURE;
        }

        $this->line('  Адрес: '.$telegram->webhookUrl());

        return $this->report($telegram->registerWebhook(), 'Готово: Telegram будет присылать сообщения на этот адрес.');
    }

    /** @param array{ok: bool, message: string} $result */
    private function report(array $result, string $success): int
    {
        if ($result['ok']) {
            $this->components->info($success);

            return self::SUCCESS;
        }

        $this->components->error($result['message']);

        return self::FAILURE;
    }

    private function info_(TelegramGateway $telegram): int
    {
        $info = $telegram->webhookInfo();

        if ($info === null) {
            $this->components->error('Telegram не ответил. Проверьте TELEGRAM_BOT_TOKEN и доступ в интернет с этого сервера.');

            return self::FAILURE;
        }

        $url = (string) ($info['url'] ?? '');

        $this->components->twoColumnDetail('Адрес у Telegram', $url !== '' ? $url : 'не задан');
        $this->components->twoColumnDetail('Ожидает доставки', (string) ($info['pending_update_count'] ?? 0));

        if (filled($info['last_error_message'] ?? null)) {
            $this->components->twoColumnDetail('Последняя ошибка', (string) $info['last_error_message']);
        }

        $expected = $telegram->webhookUrl();

        if ($expected !== null && $url !== $expected) {
            $this->newLine();
            $this->components->warn('Адрес отличается от нынешних настроек: '.$expected);
            $this->line('  Выполните «php artisan telegram:webhook», чтобы привести их в соответствие.');
        }

        return self::SUCCESS;
    }
}
