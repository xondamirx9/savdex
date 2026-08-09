<?php

declare(strict_types=1);

namespace Tests\Support;

use Illuminate\Notifications\Notification;

/**
 * Простейшее уведомление в базу — для проверки, что штатный механизм
 * Laravel работает и наше отношение alerts() его не перекрывает.
 */
class DatabaseNotification extends Notification
{
    /** @return list<string> */
    public function via(object $notifiable): array
    {
        return ['database'];
    }

    /** @return array<string, string> */
    public function toDatabase(object $notifiable): array
    {
        return ['title' => 'Выгрузка готова'];
    }
}
