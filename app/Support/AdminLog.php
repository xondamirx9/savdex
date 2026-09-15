<?php

declare(strict_types=1);

namespace App\Support;

use App\Models\AdminAction;
use App\Models\User;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Support\Facades\Auth;
use Illuminate\Support\Facades\Request;

/**
 * Запись в журнал действий администраторов.
 *
 * Одна точка входа для всего: и для наблюдателя, который ловит обычные
 * правки, и для служб, которым нужно записать решение по-человечески —
 * «одобрил документ», а не «изменил поле moderation_status».
 *
 * Journal никогда не должен ронять действие, которое он записывает.
 * Если запись не удалась, действие уже совершено, и падать поздно.
 */
final class AdminLog
{
    /**
     * Поля, которые в журнал не попадают ни при каких обстоятельствах.
     *
     * Пароль в истории изменений — это пароль, лежащий в базе открыто,
     * только в другой таблице и навсегда.
     */
    private const SECRET = [
        'password', 'remember_token', 'two_factor_secret',
        'two_factor_recovery_codes', 'api_token',
    ];

    /** Шум: меняются при каждом сохранении и ничего не сообщают. */
    private const NOISE = ['updated_at', 'created_at', 'search_text'];

    /**
     * @param  array{before?: array<string, mixed>, after?: array<string, mixed>}  $changes
     */
    public static function record(
        string $action,
        string $section,
        ?Model $subject = null,
        array $changes = [],
        ?string $note = null,
        ?User $actor = null,
    ): void {
        try {
            $actor ??= Auth::user() instanceof User ? Auth::user() : null;

            AdminAction::create([
                'user_id' => $actor?->getKey(),
                // Снимок имени: ссылка умрёт вместе с удалённым сотрудником,
                // а вопрос «кто это сделал» задают как раз после увольнения
                'user_name' => mb_substr($actor?->name ?? 'консоль', 0, 120),
                'user_role' => $actor?->admin_role,
                'action' => $action,
                'section' => $section,
                'subject_type' => $subject !== null ? $subject::class : null,
                'subject_id' => $subject?->getKey(),
                'subject_label' => $subject !== null ? self::label($subject) : null,
                'changes' => self::clean($changes) ?: null,
                'note' => $note,
                'ip' => Request::ip(),
            ]);
        } catch (\Throwable $e) {
            // Действие уже совершено — падать поздно. Но и молчать нельзя:
            // незаписанное действие должно оставить след хотя бы в логах.
            report($e);
        }
    }

    /**
     * Пишет ли наблюдатель эту правку.
     *
     * Только действия администратора в панели. Правка своей карточки
     * владельцем компании — не действие администратора, и журналу,
     * который ведётся ради проверки сотрудников, она только мешает.
     */
    public static function actorIsAdmin(): bool
    {
        $user = Auth::user();

        return $user instanceof User && $user->is_admin;
    }

    /** Понятное название записи: имя компании, заголовок объявления, почта. */
    public static function label(Model $subject): string
    {
        foreach (['name', 'title', 'email', 'code', 'slug'] as $field) {
            $value = $subject->getAttribute($field);

            if (is_string($value) && $value !== '') {
                return mb_substr($value, 0, 200);
            }
        }

        return class_basename($subject).' #'.$subject->getKey();
    }

    /**
     * Значение поля словами — для таблицы «было / стало».
     *
     * Пустое поле и поле со строкой «null» — разные вещи, и человек,
     * который смотрит журнал, должен их различать.
     */
    public static function readable(mixed $value): string
    {
        return match (true) {
            $value === null => '—',
            $value === '' => '(пусто)',
            is_bool($value) => $value ? 'да' : 'нет',
            is_array($value) => json_encode($value, JSON_UNESCAPED_UNICODE) ?: '—',
            default => (string) $value,
        };
    }

    /**
     * Убрать из истории секреты и шум.
     *
     * @param  array{before?: array<string, mixed>, after?: array<string, mixed>}  $changes
     * @return array{before?: array<string, mixed>, after?: array<string, mixed>}
     */
    private static function clean(array $changes): array
    {
        $cleaned = [];

        foreach (['before', 'after'] as $side) {
            foreach ($changes[$side] ?? [] as $field => $value) {
                if (in_array($field, self::NOISE, true)) {
                    continue;
                }

                $cleaned[$side][$field] = in_array($field, self::SECRET, true)
                    ? '···'
                    : self::shorten($value);
            }
        }

        return $cleaned;
    }

    /**
     * Длинные значения обрезаются.
     *
     * Описание компании на десять тысяч знаков, сохранённое дважды, —
     * это двадцать тысяч знаков в журнале ради одной исправленной опечатки.
     */
    private static function shorten(mixed $value): mixed
    {
        if (is_string($value) && mb_strlen($value) > 300) {
            return mb_substr($value, 0, 300).'…';
        }

        return $value;
    }
}
