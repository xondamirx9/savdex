<?php

declare(strict_types=1);

namespace App\Observers;

use App\Support\AdminLog;
use Illuminate\Database\Eloquent\Model;

/**
 * Ловит правки, сделанные администратором в панели.
 *
 * Один наблюдатель на все наблюдаемые модели: раздел прав берётся из
 * карты в AppServiceProvider, а не из имени класса. Угадывать раздел по
 * имени модели значит однажды угадать неверно и потерять записи там,
 * где их ищут.
 *
 * Решения по существу — «одобрил», «вернул на исправление», «выдал
 * право» — пишут сами службы через AdminLog. Наблюдатель знает только
 * «создано, изменено, удалено» и что именно поменялось.
 */
class AuditObserver
{
    /** @var array<class-string, string> модель → раздел прав */
    private static array $sections = [];

    /**
     * @param  array<class-string, string>  $sections
     */
    public static function watch(array $sections): void
    {
        self::$sections = $sections;
    }

    public function created(Model $model): void
    {
        $this->write('created', $model, ['after' => $model->getAttributes()]);
    }

    public function updated(Model $model): void
    {
        $changed = $model->getChanges();

        if ($changed === []) {
            return;
        }

        $this->write($this->name($model, $changed), $model, [
            'before' => array_intersect_key($model->getRawOriginal(), $changed),
            'after' => $changed,
        ]);
    }

    /**
     * Блокировка называется блокировкой, а не «изменением».
     *
     * Технически это правка одного поля, но ищут её не так: вопрос
     * звучит «кто заблокировал эту компанию», и ответ должен находиться
     * фильтром по действию, а не чтением истории изменений подряд.
     *
     * @param  array<string, mixed>  $changed
     */
    private function name(Model $model, array $changed): string
    {
        if (! array_key_exists('status', $changed)) {
            return 'updated';
        }

        return match (true) {
            $changed['status'] === 'blocked' => 'blocked',
            $model->getRawOriginal('status') === 'blocked' => 'unblocked',
            default => 'updated',
        };
    }

    public function deleted(Model $model): void
    {
        $this->write('deleted', $model);
    }

    public function restored(Model $model): void
    {
        $this->write('restored', $model);
    }

    /**
     * @param  array{before?: array<string, mixed>, after?: array<string, mixed>}  $changes
     */
    private function write(string $action, Model $model, array $changes = []): void
    {
        if (! AdminLog::actorIsAdmin()) {
            return;
        }

        $section = self::$sections[$model::class] ?? null;

        if ($section === null) {
            return;
        }

        AdminLog::record($action, $section, $model, $changes);
    }
}
