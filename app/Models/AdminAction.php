<?php

declare(strict_types=1);

namespace App\Models;

use App\Support\AdminAccess;
use Illuminate\Database\Eloquent\Attributes\Fillable;
use Illuminate\Database\Eloquent\Builder;
use Illuminate\Database\Eloquent\MassPrunable;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;
use Illuminate\Database\Eloquent\Relations\MorphTo;
use RuntimeException;

/**
 * Запись журнала действий администраторов.
 *
 * Запись создаётся и больше не меняется — ни правкой, ни удалением, и
 * никем, включая суперадмина. Журнал, который можно подчистить, защищает
 * ровно до того момента, когда он понадобится.
 *
 * Запрет стоит в модели, а не только в правах: права закрывают панель,
 * а модель — ещё и команду в консоли, и случайный код обслуживания.
 */
#[Fillable([
    'user_id', 'user_name', 'user_role', 'action', 'section',
    'subject_type', 'subject_id', 'subject_label', 'changes', 'note', 'ip',
])]
class AdminAction extends Model
{
    use MassPrunable;

    /** Записи не меняются, значит и отметке об изменении взяться неоткуда. */
    public const UPDATED_AT = null;

    /** @var array<string, string> */
    public const ACTIONS = [
        'created' => 'Создание',
        'updated' => 'Изменение',
        'deleted' => 'Удаление',
        'restored' => 'Восстановление',
        'approved' => 'Одобрение',
        'rejected' => 'Отклонение',
        'returned' => 'Возврат на исправление',
        'hidden' => 'Скрытие',
        'blocked' => 'Блокировка',
        'unblocked' => 'Разблокировка',
        'granted' => 'Выдача прав',
        'revoked' => 'Отзыв прав',
        'exported' => 'Выгрузка',
        'imported' => 'Загрузка',
        'refunded' => 'Возврат средств',
        'paid' => 'Проведение оплаты',
    ];

    protected static function booted(): void
    {
        static::updating(static function (): never {
            throw new RuntimeException('Записи журнала действий не изменяются.');
        });

        static::deleting(static function (): never {
            throw new RuntimeException('Записи журнала действий не удаляются.');
        });
    }

    protected function casts(): array
    {
        return [
            'changes' => 'array',
            'created_at' => 'datetime',
        ];
    }

    /**
     * Срок хранения — год.
     *
     * Дальше журнал отвечает на вопросы, которых уже никто не задаёт, а
     * растёт с каждым действием каждого сотрудника.
     *
     * Массовое удаление, а не поштучное: оно идёт запросом, минуя события
     * модели, и потому не спотыкается о запрет на удаление. Обслуживание
     * по расписанию и правка живого журнала — разные вещи.
     */
    public function prunable(): Builder
    {
        return static::where('created_at', '<', now()->subYear());
    }

    public function user(): BelongsTo
    {
        return $this->belongsTo(User::class)->withTrashed();
    }

    public function subject(): MorphTo
    {
        return $this->morphTo();
    }

    public function actionLabel(): string
    {
        return self::ACTIONS[$this->action] ?? $this->action;
    }

    public function sectionLabel(): string
    {
        return AdminAccess::SECTIONS[$this->section] ?? $this->section;
    }
}
