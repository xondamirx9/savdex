<?php

declare(strict_types=1);

namespace App\Support;

use App\Models\ActivityEvent;
use App\Models\Broadcast;
use App\Models\Company;
use App\Models\User;
use App\Models\UserNotification;
use Illuminate\Database\Eloquent\Builder;
use Illuminate\Support\Facades\DB;

/**
 * Создание уведомлений.
 *
 * Единая точка: событие в компании почти всегда должно порождать
 * и запись в ленте, и персональные уведомления сотрудникам. Разнесённое
 * по контроллерам, это рассинхронизируется на третьем же месте.
 */
class Notifier
{
    /**
     * Уведомить всех сотрудников компании и записать событие в ленту.
     *
     * @param  array<string, mixed>  $attributes
     */
    public function company(Company $company, string $type, string $title, array $attributes = []): void
    {
        ActivityEvent::create([
            'company_id' => $company->id,
            'type' => $type,
            'tone' => $attributes['tone'] ?? 'info',
            'message' => $title,
            'url' => $attributes['url'] ?? null,
        ]);

        foreach ($company->users()->get() as $user) {
            UserNotification::deliver($user, [
                'type' => $type,
                'title' => $title,
                ...$attributes,
            ]);
        }
    }

    /** @param array<string, mixed> $attributes */
    public function user(User $user, string $type, string $title, array $attributes = []): UserNotification
    {
        return UserNotification::deliver($user, ['type' => $type, 'title' => $title, ...$attributes]);
    }

    /**
     * Рассылка администратора по сегменту.
     *
     * Вставка пачками по 500: рассылка на всю базу одним запросом
     * упирается в лимит плейсхолдеров, а по одной строке — в время
     * ответа админки.
     */
    public function broadcast(Broadcast $broadcast): int
    {
        $query = $this->audienceQuery($broadcast);
        $now = now();
        $total = 0;

        $query->chunkById(500, function ($users) use ($broadcast, $now, &$total): void {
            /*
             * Значения по умолчанию подставляются здесь, а не берутся
             * из схемы: вставка идёт через DB::table в обход модели,
             * и дефолты БД не применяются к колонкам, переданным явно.
             * Свежесозданный Broadcast без tone держит null в атрибуте,
             * пока его не перечитали, — и вставка падала на NOT NULL.
             */
            $rows = $users->map(fn (User $u): array => [
                'user_id' => $u->id,
                'company_id' => $u->company_id,
                'type' => UserNotification::TYPE_BROADCAST,
                'tone' => $broadcast->tone ?? 'info',
                'title' => $broadcast->title,
                'body' => $broadcast->body,
                'url' => $broadcast->url,
                'sent_by' => $broadcast->sent_by,
                'is_broadcast' => true,
                'created_at' => $now,
                'updated_at' => $now,
            ])->all();

            DB::table('user_notifications')->insert($rows);
            $total += count($rows);
        });

        $broadcast->forceFill(['recipients_count' => $total, 'sent_at' => $now])->save();

        return $total;
    }

    /** @return Builder<User> */
    private function audienceQuery(Broadcast $broadcast): Builder
    {
        $query = User::query()->where('status', 'active');

        return match ($broadcast->audience) {
            'plan' => $query->whereHas('company.subscription.plan',
                fn ($q) => $q->where('code', $broadcast->audience_value)),
            'verified' => $query->whereHas('company', fn ($q) => $q->where('verification_level', '>', 0)),
            'unverified' => $query->whereHas('company', fn ($q) => $q->where('verification_level', 0)),
            'no_company' => $query->whereNull('company_id'),
            default => $query,
        };
    }
}
