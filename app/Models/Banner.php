<?php

declare(strict_types=1);

namespace App\Models;

use App\Support\Business;
use Illuminate\Database\Eloquent\Attributes\Fillable;
use Illuminate\Database\Eloquent\Builder;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\HasMany;
use Illuminate\Support\Carbon;

/**
 * Баннер: акция или объявление площадки на видном месте.
 *
 * Заводится целиком из админки — картинка, срок, место, ссылка. До
 * этого главная состояла из семи неизменяемых блоков, и полоса
 * «Скидка до 1 октября» означала задачу разработчику и деплой.
 */
#[Fillable([
    'name', 'placement', 'url', 'alt',
    'image_path', 'image_mobile_path', 'focal_x', 'focal_y',
    'starts_at', 'ends_at', 'is_active', 'is_dismissible', 'sort',
])]
class Banner extends Model
{
    /** Главная, сразу под первым экраном. */
    public const PLACEMENT_HOME = 'home';

    /** Каталог объявлений, над списком товаров. */
    public const PLACEMENT_CATALOG = 'catalog';

    /** @var array<string, string> */
    public const PLACEMENTS = [
        self::PLACEMENT_HOME => 'Главная страница',
        self::PLACEMENT_CATALOG => 'Каталог объявлений',
    ];

    /**
     * Сколько дней закрытый баннер не показывается снова.
     *
     * Насовсем прятать нельзя: человек закрывает крестик по привычке
     * и больше не узнаёт про акцию. Возвращать каждый день — навязчиво.
     * Трое суток: напомнит раз, но не примелькается.
     */
    public const DISMISS_DAYS = 3;

    /**
     * Умолчания повторяют умолчания столбцов.
     *
     * Без них только что созданный объект отличается от того же
     * объекта, прочитанного из базы: столбец получает значение при
     * вставке, а свойство остаётся пустым. Проверка «показывается ли
     * баннер» на таком объекте отвечала «нет» на исправном баннере.
     *
     * @var array<string, mixed>
     */
    protected $attributes = [
        'is_active' => true,
        'is_dismissible' => true,
        'focal_x' => 50,
        'focal_y' => 50,
        'sort' => 0,
    ];

    protected function casts(): array
    {
        return [
            'starts_at' => 'datetime',
            'ends_at' => 'datetime',
            'is_active' => 'boolean',
            'is_dismissible' => 'boolean',
            'focal_x' => 'integer',
            'focal_y' => 'integer',
            'sort' => 'integer',
        ];
    }

    /** Картинки под отдельные языки; основная лежит на самом баннере. */
    public function images(): HasMany
    {
        return $this->hasMany(BannerImage::class);
    }

    /**
     * Баннеры, которые показываются прямо сейчас.
     *
     * Срок закончился — баннер исчезает сам, снимать руками не нужно:
     * акция, провисевшая лишний день, это обещание, которого площадка
     * уже не выполняет.
     *
     * @param  Builder<self>  $query
     */
    public function scopeLive(Builder $query, ?Carbon $now = null): void
    {
        $now ??= Carbon::now();

        $query->where('is_active', true)
            ->where(fn (Builder $q) => $q->whereNull('starts_at')->orWhere('starts_at', '<=', $now))
            ->where(fn (Builder $q) => $q->whereNull('ends_at')->orWhere('ends_at', '>', $now));
    }

    /**
     * Баннер места — ровно один.
     *
     * Два баннера подряд отпугивают сильнее, чем помогает второй,
     * поэтому лишний ждёт своей очереди: показывается тот, у кого
     * меньше «порядок», а при равенстве — заведённый позже.
     */
    public static function forPlacement(string $placement, ?Carbon $now = null): ?self
    {
        return self::query()
            ->live($now)
            ->where('placement', $placement)
            ->with('images')
            ->orderBy('sort')
            ->orderByDesc('id')
            ->first();
    }

    /** Картинка на языке страницы, с откатом на основную. */
    public function imageFor(?string $locale = null): string
    {
        return $this->localised($locale)?->image_path ?? $this->image_path;
    }

    /**
     * Мобильная картинка на языке страницы.
     *
     * Откат хитрее, чем у основной: если под язык загрузили только
     * широкую картинку, брать мобильную от другого языка нельзя —
     * на ней будет чужой текст. Тогда лучше обрезать свою по точке
     * фокуса, то есть вернуть null.
     */
    public function mobileImageFor(?string $locale = null): ?string
    {
        $localised = $this->localised($locale);

        return $localised !== null
            ? $localised->image_mobile_path
            : $this->image_mobile_path;
    }

    private function localised(?string $locale): ?BannerImage
    {
        $locale ??= app()->getLocale();

        return $this->images->firstWhere('locale', $locale);
    }

    /** Идёт ли баннер прямо сейчас — для подписи в админке. */
    public function isLive(?Carbon $now = null): bool
    {
        $now ??= Carbon::now();

        return $this->is_active
            && ($this->starts_at === null || $this->starts_at->lessThanOrEqualTo($now))
            && ($this->ends_at === null || $this->ends_at->greaterThan($now));
    }

    /**
     * Сколько осталось до конца акции — человеческой фразой.
     *
     * Ради этого столбца в таблице всё и затевалось: «до 30 октября»
     * не говорит, пора ли готовить следующую, а «осталось 2 дня»
     * говорит.
     */
    public function countdown(?Carbon $now = null): string
    {
        $now ??= Carbon::now();

        if ($this->ends_at === null) {
            return 'бессрочно';
        }

        if ($this->ends_at->lessThanOrEqualTo($now)) {
            return 'закончилась';
        }

        if ($this->starts_at !== null && $this->starts_at->greaterThan($now)) {
            return 'старт '.Business::local($this->starts_at)->translatedFormat('d MMMM');
        }

        $left = $now->diffInDays($this->ends_at, absolute: true);

        if ($left >= 1) {
            return 'осталось '.trans_choice(':count день|:count дня|:count дней', (int) $left, ['count' => (int) $left]);
        }

        $hours = (int) $now->diffInHours($this->ends_at, absolute: true);

        return $hours >= 1
            ? 'осталось '.trans_choice(':count час|:count часа|:count часов', $hours, ['count' => $hours])
            : 'меньше часа';
    }
}
