<?php

declare(strict_types=1);

namespace App\Support;

use App\Models\Company;
use App\Models\ContactUnlock;
use App\Models\Listing;
use App\Models\Payment;
use App\Models\Review;
use App\Models\User;
use Illuminate\Support\Carbon;
use Illuminate\Support\Facades\DB;

/**
 * Продуктовые показатели площадки для инфопанели админки.
 *
 * Считает то, по чему принимают решения о продукте, а не то, что
 * проще достать. «Всего компаний» растёт всегда и ни о чём не говорит;
 * «доля дошедших до первого объявления» показывает, где люди отваливаются.
 */
class PlatformMetrics
{
    public function __construct(private readonly int $days = 30) {}

    private function from(): Carbon
    {
        return Carbon::today()->subDays($this->days - 1);
    }

    /**
     * Воронка регистрации: где именно теряются люди.
     *
     * @return list<array{label: string, value: int, share: float, hint: string}>
     */
    public function activationFunnel(): array
    {
        $registered = User::query()->count();

        $verified = User::query()->whereNotNull('email_verified_at')->count();
        $withCompany = User::query()->whereNotNull('company_id')->count();

        $withListing = User::query()
            ->whereHas('company.listings')
            ->count();

        $withActive = User::query()
            ->whereHas('company.listings', fn ($q) => $q->where('status', Listing::STATUS_ACTIVE))
            ->count();

        $top = max(1, $registered);

        $steps = [
            ['Зарегистрировались', $registered, 'все аккаунты за всё время'],
            ['Подтвердили почту', $verified, 'без подтверждения публикация закрыта'],
            ['Завели компанию', $withCompany, 'второй шаг регистрации, он пропускаемый'],
            ['Создали объявление', $withListing, 'включая черновики и отклонённые'],
            ['Дошли до публикации', $withActive, 'объявление реально видно покупателям'],
        ];

        return array_map(fn (array $s): array => [
            'label' => $s[0],
            'value' => $s[1],
            'share' => round($s[1] / $top * 100, 1),
            'hint' => $s[2],
        ], $steps);
    }

    /**
     * Ключевые показатели с изменением к прошлому периоду.
     *
     * @return array<string, array{value: int|float, delta: float|null, suffix: string}>
     */
    public function summary(): array
    {
        $now = $this->from();
        $prev = $now->copy()->subDays($this->days);

        $count = fn (string $model, ?Carbon $from, ?Carbon $to = null): int => $model::query()
            ->when($from !== null, fn ($q) => $q->where('created_at', '>=', $from))
            ->when($to !== null, fn ($q) => $q->where('created_at', '<', $to))
            ->count();

        $revenue = fn (?Carbon $from, ?Carbon $to = null): int => (int) Payment::query()
            ->where('status', 'paid')
            ->when($from !== null, fn ($q) => $q->where('paid_at', '>=', $from))
            ->when($to !== null, fn ($q) => $q->where('paid_at', '<', $to))
            ->sum('amount');

        return [
            'companies' => $this->metric(
                $count(Company::class, $now),
                $count(Company::class, $prev, $now),
                ' компаний',
            ),
            'listings' => $this->metric(
                $count(Listing::class, $now),
                $count(Listing::class, $prev, $now),
                ' объявлений',
            ),
            'unlocks' => $this->metric(
                $count(ContactUnlock::class, $now),
                $count(ContactUnlock::class, $prev, $now),
                ' раскрытий',
            ),
            'revenue' => $this->metric($revenue($now), $revenue($prev, $now), ' сум'),
        ];
    }

    /** @return array{value: int|float, delta: float|null, suffix: string} */
    private function metric(int|float $now, int|float $prev, string $suffix): array
    {
        return [
            'value' => $now,
            // null, когда сравнивать не с чем: «+100 %» от нуля — неправда
            'delta' => $prev > 0 ? round(($now - $prev) / $prev * 100, 1) : null,
            'suffix' => $suffix,
        ];
    }

    /**
     * Здоровье площадки: показатели, по которым видно проблему раньше,
     * чем она отразится на выручке.
     *
     * @return list<array{label: string, value: string, tone: string, hint: string}>
     */
    public function health(): array
    {
        $activeCompanies = Company::query()->where('status', 'active')->count();

        $withActiveListings = Company::query()
            ->whereHas('listings', fn ($q) => $q->where('status', Listing::STATUS_ACTIVE))
            ->count();

        $moderationQueue = Listing::query()->where('status', Listing::STATUS_MODERATION)->count();

        $expiringSoon = Listing::query()
            ->where('status', Listing::STATUS_ACTIVE)
            ->whereNotNull('expires_at')
            ->where('expires_at', '<=', now()->addDays(7))
            ->count();

        $unansweredReviews = Review::query()
            ->whereNull('reply')
            ->where('rating', '<=', 3)
            ->count();

        $shareActive = $activeCompanies > 0
            ? round($withActiveListings / $activeCompanies * 100)
            : 0;

        return [
            [
                'label' => 'Компаний с активными объявлениями',
                'value' => "{$withActiveListings} из {$activeCompanies} ({$shareActive} %)",
                // Пустая витрина — главный риск маркетплейса: покупателю
                // нечего смотреть, и он не возвращается
                'tone' => $shareActive >= 50 ? 'success' : ($shareActive >= 25 ? 'warning' : 'danger'),
                'hint' => 'Ниже четверти — витрина выглядит пустой',
            ],
            [
                'label' => 'В очереди модерации',
                'value' => (string) $moderationQueue,
                'tone' => $moderationQueue > 20 ? 'danger' : ($moderationQueue > 5 ? 'warning' : 'success'),
                'hint' => 'Обещанный срок проверки — до 2 часов',
            ],
            [
                'label' => 'Объявлений истекает за неделю',
                'value' => (string) $expiringSoon,
                'tone' => $expiringSoon > 10 ? 'warning' : 'success',
                'hint' => 'После истечения показы прекращаются',
            ],
            [
                'label' => 'Отзывов 3★ и ниже без ответа',
                'value' => (string) $unansweredReviews,
                'tone' => $unansweredReviews > 0 ? 'warning' : 'success',
                'hint' => 'Молчание на плохой отзыв читается как согласие',
            ],
        ];
    }

    /**
     * Категории по числу объявлений — показывает, где спрос,
     * а где справочник заполнен зря.
     *
     * @return list<array{label: string, listings: int, companies: int}>
     */
    public function topCategories(int $limit = 8): array
    {
        return Listing::query()
            ->select('category_id', DB::raw('COUNT(*) as listings_count'), DB::raw('COUNT(DISTINCT company_id) as companies_count'))
            ->whereNotNull('category_id')
            ->where('status', Listing::STATUS_ACTIVE)
            ->groupBy('category_id')
            ->orderByDesc('listings_count')
            ->limit($limit)
            ->with('category.translations')
            ->get()
            ->map(fn ($row): array => [
                'label' => $row->category?->name() ?? 'Без категории',
                'listings' => (int) $row->listings_count,
                'companies' => (int) $row->companies_count,
            ])
            ->all();
    }

    /**
     * Регистрации по дням — для графика.
     *
     * @return array{labels: list<string>, companies: list<int>, users: list<int>}
     */
    public function registrationsByDay(): array
    {
        $companies = $this->countByDay(Company::class);
        $users = $this->countByDay(User::class);

        $labels = [];
        $companyRow = [];
        $userRow = [];

        for ($i = $this->days - 1; $i >= 0; $i--) {
            $date = Carbon::today()->subDays($i);
            $key = $date->toDateString();

            $labels[] = $date->translatedFormat('d.m');
            $companyRow[] = $companies[$key] ?? 0;
            $userRow[] = $users[$key] ?? 0;
        }

        return ['labels' => $labels, 'companies' => $companyRow, 'users' => $userRow];
    }

    /**
     * Число записей по дням.
     *
     * Группировка делается в PHP, а не в SQL, намеренно: функция
     * `DATE()` есть в MySQL и SQLite, но не в PostgreSQL — там нужно
     * `created_at::date`. Писать разный SQL под три СУБД ради выборки
     * за месяц не стоит того, а тесты на SQLite такое расхождение
     * не поймают в принципе: прод работает на PostgreSQL.
     *
     * Объём ограничен периодом (30 дней), поэтому чтение строк
     * вместо агрегата здесь не проблема.
     *
     * @return array<string, int>
     */
    private function countByDay(string $model): array
    {
        return $model::query()
            ->where('created_at', '>=', $this->from())
            ->pluck('created_at')
            ->groupBy(fn (Carbon $date): string => $date->toDateString())
            ->map->count()
            ->all();
    }

    /**
     * Конверсия просмотра карточки в раскрытие контакта — главный
     * показатель монетизации: именно здесь площадка зарабатывает.
     */
    public function unlockConversion(): float
    {
        $views = (int) Listing::query()->sum('views_count');
        $unlocks = ContactUnlock::query()->count();

        return $views > 0 ? round($unlocks / $views * 100, 2) : 0.0;
    }

    /** Средний чек оплаченных платежей за период. */
    public function averagePayment(): int
    {
        return (int) Payment::query()
            ->where('status', 'paid')
            ->where('paid_at', '>=', $this->from())
            ->avg('amount');
    }
}
