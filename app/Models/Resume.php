<?php

declare(strict_types=1);

namespace App\Models;

use App\Jobs\TranslateResume;
use App\Services\MachineTranslator;
use App\Support\Locales;
use App\Support\ResumeOptions;
use App\Support\SearchText;
use Illuminate\Database\Eloquent\Attributes\Fillable;
use Illuminate\Database\Eloquent\Builder;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;
use Illuminate\Database\Eloquent\SoftDeletes;
use Illuminate\Support\Carbon;
use Illuminate\Support\Facades\Storage;
use Illuminate\Support\Str;

/**
 * Резюме соискателя — одно на человека.
 *
 * Черновик виден только владельцу; опубликованное попадает в раздел
 * «Резюме» и открывается по своему адресу. Снять с публикации можно
 * в один клик: работу находят, и висящее резюме после этого приносит
 * только лишние звонки.
 */
#[Fillable([
    'title', 'field', 'country_id', 'city_id', 'salary', 'currency',
    'employment', 'schedule', 'about', 'skills', 'jobs', 'education', 'languages',
    'contact_name', 'contact_phone', 'contact_email', 'show_phone', 'show_email',
])]
class Resume extends Model
{
    use SoftDeletes;

    public const STATUS_DRAFT = 'draft';

    public const STATUS_PUBLISHED = 'published';

    public const STATUS_HIDDEN = 'hidden';

    /** Снято модерацией: сам соискатель вернуть его не может. */
    public const STATUS_BLOCKED = 'blocked';

    protected function casts(): array
    {
        return [
            'title_i18n' => 'array',
            'about_i18n' => 'array',
            'jobs_i18n' => 'array',
            'employment' => 'array',
            'schedule' => 'array',
            'skills' => 'array',
            'jobs' => 'array',
            'education' => 'array',
            'languages' => 'array',
            'show_phone' => 'boolean',
            'show_email' => 'boolean',
            'published_at' => 'datetime',
        ];
    }

    protected static function booted(): void
    {
        /*
         * Текст изменили — перевод к нему больше не подходит.
         * Старый английский заголовок у новой должности хуже, чем
         * русский: он не просто устарел, он говорит неправду.
         */
        static::saving(function (self $resume): void {
            foreach (['title', 'about', 'jobs'] as $field) {
                if ($resume->exists && $resume->isDirty($field)) {
                    $resume->{$field.'_i18n'} = null;
                }
            }
        });

        // Переводим опубликованное: черновик правят неделю, и гонять
        // переводчик на каждое сохранение незачем
        static::saved(function (self $resume): void {
            if ($resume->isPublished() && $resume->missingTranslations()
                && config('services.machine_translation.enabled')) {
                TranslateResume::dispatch($resume->id);
            }
        });
    }

    public function user(): BelongsTo
    {
        return $this->belongsTo(User::class);
    }

    public function city(): BelongsTo
    {
        return $this->belongsTo(City::class);
    }

    public function country(): BelongsTo
    {
        return $this->belongsTo(Country::class);
    }

    // ── Состояние ────────────────────────────────────────────

    public function isPublished(): bool
    {
        return $this->status === self::STATUS_PUBLISHED;
    }

    /** @param Builder<self> $query */
    public function scopePublished(Builder $query): void
    {
        $query->where('status', self::STATUS_PUBLISHED);
    }

    /**
     * Поиск по должности, навыкам и местам работы.
     *
     * Ищем по тем же правилам, что объявления: запрос набирают
     * на латинице («snabjenec»), а резюме написано кириллицей.
     *
     * @param  Builder<self>  $query
     */
    public function scopeSearch(Builder $query, string $term): void
    {
        $needles = SearchText::variants($term);

        $query->where(function (Builder $q) use ($needles): void {
            foreach ($needles as $needle) {
                $like = '%'.$needle.'%';

                $q->orWhereRaw('lower(title) like ?', [$like])
                    ->orWhereRaw('lower(about) like ?', [$like])
                    ->orWhereRaw('lower(skills) like ?', [$like])
                    ->orWhereRaw('lower(jobs) like ?', [$like]);
            }
        });
    }

    // ── Языки ────────────────────────────────────────────────

    /** Должность на языке посетителя, с откатом на оригинал. */
    public function localizedTitle(?string $locale = null): string
    {
        return $this->localized('title', $locale) ?? $this->title;
    }

    public function localizedAbout(?string $locale = null): ?string
    {
        return $this->localized('about', $locale);
    }

    /**
     * Места работы на языке посетителя.
     *
     * Перевод связан с оригиналом порядком, поэтому годится, только
     * пока мест столько же: список правили — показываем как написано,
     * а перевод соберётся заново задачей.
     *
     * @return list<array<string, mixed>>
     */
    public function localizedJobs(?string $locale = null): array
    {
        $jobs = $this->jobs ?? [];
        $locale ??= app()->getLocale();
        $translated = ($this->jobs_i18n ?? [])[$locale] ?? null;

        if (! is_array($translated) || count($translated) !== count($jobs)) {
            return $jobs;
        }

        return array_map(
            fn (array $job, array $row): array => [
                ...$job,
                'position' => filled($row['position'] ?? null) ? $row['position'] : $job['position'] ?? '',
                'duties' => filled($row['duties'] ?? null) ? $row['duties'] : $job['duties'] ?? '',
            ],
            $jobs,
            $translated,
        );
    }

    private function localized(string $field, ?string $locale): ?string
    {
        $locale ??= app()->getLocale();
        $original = $this->{$field};

        if ($locale === Locales::DEFAULT) {
            return $original;
        }

        $translated = ($this->{$field.'_i18n'} ?? [])[$locale] ?? null;

        return filled($translated) ? $translated : $original;
    }

    /** Есть ли язык, на который резюме ещё не переведено. */
    public function missingTranslations(): bool
    {
        foreach (MachineTranslator::TARGETS as $locale) {
            if (blank(($this->title_i18n ?? [])[$locale] ?? null)) {
                return true;
            }
        }

        return false;
    }

    /**
     * Резюме, которым не хватает переводов, — для ежечасного добора.
     *
     * @param  Builder<self>  $query
     */
    public function scopeLackingTranslations(Builder $query): void
    {
        $query->where(function (Builder $q): void {
            foreach (MachineTranslator::TARGETS as $locale) {
                $q->orWhereJsonDoesntContainKey('title_i18n->'.$locale);
            }
        });
    }

    // ── Производные значения ─────────────────────────────────

    /**
     * Опыт в месяцах — сумма периодов всех мест работы.
     *
     * Пересекающиеся места не складываются дважды: человек, который
     * год работал на двух работах сразу, получил бы два года опыта,
     * и фильтр «от трёх лет» перестал бы значить хоть что-то.
     *
     * @param  list<array<string, mixed>>|null  $jobs
     */
    public static function experienceMonths(?array $jobs): int
    {
        $periods = [];

        foreach ($jobs ?? [] as $job) {
            $start = self::month($job['start'] ?? null);

            if ($start === null) {
                continue;
            }

            // Пустой конец — «по настоящее время»
            $end = self::month($job['end'] ?? null) ?? Carbon::now()->startOfMonth();

            if ($end->lt($start)) {
                continue;
            }

            $periods[] = [$start, $end];
        }

        usort($periods, fn (array $a, array $b): int => $a[0] <=> $b[0]);

        $months = 0;
        $cursor = null;

        foreach ($periods as [$start, $end]) {
            if ($cursor !== null && $start->lte($cursor)) {
                $start = $cursor->copy();
            }

            if ($end->lte($start)) {
                continue;
            }

            $months += (int) $start->diffInMonths($end);
            $cursor = $end->copy();
        }

        return min($months, 65_000);
    }

    /** «2019-04» или «2019» — в первое число месяца; мусор — null. */
    private static function month(mixed $value): ?Carbon
    {
        $raw = trim((string) $value);

        if (preg_match('/^(\d{4})(?:-(\d{1,2}))?/', $raw, $m) !== 1) {
            return null;
        }

        $year = (int) $m[1];
        $month = isset($m[2]) ? max(1, min(12, (int) $m[2])) : 1;

        if ($year < 1950 || $year > (int) date('Y') + 1) {
            return null;
        }

        return Carbon::create($year, $month, 1)->startOfMonth();
    }

    /** Опыт словами: «5 лет 2 месяца» собирает витрина, здесь — числа. */
    public function experience(): array
    {
        return [
            'years' => intdiv($this->experience_months, 12),
            'months' => $this->experience_months % 12,
        ];
    }

    public function photoUrl(): ?string
    {
        return $this->photo_path === null ? null : Storage::disk('public')->url($this->photo_path);
    }

    public function initials(): string
    {
        $name = trim((string) ($this->contact_name ?: $this->user?->name));

        $letters = collect(preg_split('/\s+/u', $name) ?: [])
            ->filter()
            ->take(2)
            ->map(fn (string $word): string => mb_strtoupper(mb_substr($word, 0, 1)))
            ->implode('');

        return $letters !== '' ? $letters : '—';
    }

    /** Подходит ли резюме под ступень опыта из фильтра. */
    public static function experienceAtLeast(string $step): int
    {
        return ResumeOptions::EXPERIENCE_STEPS[$step] ?? 0;
    }

    public static function makeSlug(string $title, int $id): string
    {
        $base = Str::slug(Str::transliterate($title));

        return Str::limit($base, 60, '').'-'.$id;
    }
}
