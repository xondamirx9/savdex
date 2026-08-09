<?php

declare(strict_types=1);

namespace Database\Seeders;

use App\Models\ActivityEvent;
use App\Models\Category;
use App\Models\Company;
use App\Models\ContactUnlock;
use App\Models\Listing;
use App\Models\ListingStat;
use App\Models\Payment;
use App\Models\PaymentMethod;
use App\Models\Plan;
use App\Models\Promotion;
use App\Models\PromotionType;
use App\Models\Review;
use App\Models\SearchHit;
use App\Models\Subscription;
use App\Models\User;
use App\Models\UserNotification;
use App\Models\Wallet;
use Illuminate\Database\Seeder;
use Illuminate\Support\Carbon;
use Illuminate\Support\Facades\DB;

/**
 * Наполнение кабинета демонстрационной компании.
 *
 * Цифры подобраны так, чтобы каждый раздел показывал осмысленную
 * картину: объявления во всех статусах, контакты на разных стадиях
 * воронки, отзыв с ответом и без, продвижение с уже посчитанным
 * эффектом. На пустых таблицах интерфейс нечем проверить.
 */
class CabinetDemoSeeder extends Seeder
{
    public function run(): void
    {
        $company = Company::query()->where('name', 'ООО «Стройбаза»')->first();

        if ($company === null) {
            $this->command?->warn('Нет демо-компании — сначала DemoSeeder.');

            return;
        }

        $user = User::query()->where('email', 'demo@savdex.uz')->first();

        DB::transaction(function () use ($company, $user): void {
            $this->subscribe($company);
            $listings = $this->listings($company, $user);
            $this->stats($listings);
            $this->unlocks($company, $listings);
            $this->reviews($company, $listings);
            $this->promotions($company, $listings);
            $this->payments($company);
            $this->events($company);
            $this->notifications($user);
            $this->searchHits($company);
        });

        $this->command?->info('Кабинет наполнен: '.$company->name);
    }

    private function subscribe(Company $company): void
    {
        $plan = Plan::query()->where('code', 'business')->firstOrFail();

        Subscription::updateOrCreate(
            ['company_id' => $company->id, 'status' => 'active'],
            [
                'plan_id' => $plan->id,
                'started_at' => now()->subDays(2),
                'ends_at' => now()->addDays(28),
                'auto_renew' => true,
            ],
        );

        Wallet::updateOrCreate(
            ['company_id' => $company->id],
            [
                'credits' => 12,
                'promo_units' => 38,
                'contacts_used_this_period' => 38,
                'period_resets_at' => now()->addDays(28),
            ],
        );
    }

    /** @return array<string, Listing> */
    private function listings(Company $company, ?User $user): array
    {
        $cement = Category::query()->where('slug', 'cement-beton')->first();
        $pallets = Category::query()->where('slug', 'poddony-tara')->first();
        $metal = Category::query()->where('slug', 'metalloprokat')->first();

        $rows = [
            'cement' => [
                'title' => 'Цемент М400 навалом и в мешках 50 кг, отгрузка с завода',
                'category_id' => $cement?->id,
                'type' => Listing::TYPE_SUPPLY,
                'price' => 1_200_000,
                'unit' => 'т',
                'status' => Listing::STATUS_ACTIVE,
                'published_at' => now()->subDays(62),
                'expires_at' => now()->addDays(92),
                'impressions_count' => 1842,
                'views_count' => 286,
                'unlocks_count' => 14,
                'favorites_count' => 31,
                'description' => 'Портландцемент М400 Д20 с завода в Бекабаде. Отгрузка навалом цементовозами и в мешках по 50 кг. Паспорт качества на каждую партию. Минимальная партия — 20 тонн.',
            ],
            'gravel' => [
                'title' => 'Щебень фракция 5–20, отгрузка с карьера',
                'category_id' => $cement?->id,
                'type' => Listing::TYPE_SUPPLY,
                'price' => 420_000,
                'unit' => 'м³',
                'status' => Listing::STATUS_ACTIVE,
                // Истекает через три дня — в списке подсвечивается красным
                'published_at' => now()->subDays(87),
                'expires_at' => now()->addDays(3),
                'impressions_count' => 964,
                'views_count' => 118,
                'unlocks_count' => 5,
                'favorites_count' => 12,
                'description' => 'Щебень гранитный фракции 5–20 мм с собственного карьера. Самовывоз или доставка по Ташкентской области.',
            ],
            'pallets' => [
                'title' => 'Куплю поддоны деревянные 1200×800, 2 000 шт',
                'category_id' => $pallets?->id,
                'type' => Listing::TYPE_DEMAND,
                'price' => null,
                'price_negotiable' => true,
                'unit' => 'шт',
                'status' => Listing::STATUS_ACTIVE,
                'published_at' => now()->subDays(14),
                'expires_at' => now()->addDays(48),
                'impressions_count' => 612,
                'views_count' => 94,
                'unlocks_count' => 4,
                'favorites_count' => 7,
                'description' => 'Закупаем поддоны 1200×800 первого и второго сорта. Регулярные объёмы, самовывоз из Ташкента.',
            ],
            'moderation' => [
                'title' => 'Арматура А500С диаметр 12 мм, прокат в бухтах',
                'category_id' => $metal?->id,
                'type' => Listing::TYPE_SUPPLY,
                'price' => 8_900_000,
                'unit' => 'т',
                'status' => Listing::STATUS_MODERATION,
                'published_at' => null,
                'expires_at' => null,
                'description' => 'Арматура строительная А500С. Резка в размер, доставка манипулятором.',
            ],
            'draft' => [
                'title' => 'Кирпич керамический полнотелый М150',
                'category_id' => null,
                'type' => Listing::TYPE_SUPPLY,
                'status' => Listing::STATUS_DRAFT,
                'wizard_step' => 2,
                'description' => null,
            ],
            'expired' => [
                'title' => 'Песок карьерный мытый, сезонная отгрузка',
                'category_id' => $cement?->id,
                'type' => Listing::TYPE_SUPPLY,
                'price' => 180_000,
                'unit' => 'м³',
                'status' => Listing::STATUS_EXPIRED,
                'published_at' => now()->subDays(160),
                'expires_at' => now()->subDays(12),
                'impressions_count' => 431,
                'views_count' => 52,
                'unlocks_count' => 2,
                'description' => 'Песок мытый для бетонных работ.',
            ],
            'rejected' => [
                'title' => 'Цемент оптом дёшево',
                'category_id' => $cement?->id,
                'type' => Listing::TYPE_SUPPLY,
                'status' => Listing::STATUS_REJECTED,
                // Причина отказа — из прототипа: телефон в тексте объявления
                'moderation_note' => 'В тексте указан номер телефона. Контакты передаются только через раскрытие контактов площадки.',
                'description' => 'Продаём цемент, звоните по телефону в описании.',
            ],
        ];

        $result = [];

        foreach ($rows as $key => $data) {
            $listing = Listing::query()->firstOrNew([
                'company_id' => $company->id,
                'title' => $data['title'],
            ]);

            $listing->fill([
                ...$data,
                'company_id' => $company->id,
                'user_id' => $user?->id,
                'city_id' => $company->city_id,
                'currency' => 'UZS',
            ]);

            $listing->save();

            // Адрес строится после сохранения: в него входит id
            if (blank($listing->slug)) {
                $listing->slug = Listing::makeSlug($listing->title, $listing->id);
                $listing->save();
            }

            if (isset($data['moderation_note'])) {
                $listing->moderation_note = $data['moderation_note'];
                $listing->save();
            }

            $result[$key] = $listing;
        }

        return $result;
    }

    /**
     * Статистика за 60 дней с восходящим трендом и недельной волной.
     *
     * Именно 60, а не 30: кабинет сравнивает период с предыдущим таким же.
     * На тридцати днях предыдущий период оказывается пустым, и прирост
     * выходит вида «+1407 %» — цифра, по которой сразу видно, что данные
     * выдуманы. Ровные числа выдают то же самое, поэтому есть тренд
     * и спад на выходных.
     *
     * @param  array<string, Listing>  $listings
     */
    private function stats(array $listings): void
    {
        foreach (['cement' => 1.0, 'gravel' => 0.55, 'pallets' => 0.35] as $key => $weight) {
            $listing = $listings[$key];

            for ($day = 59; $day >= 0; $day--) {
                $date = Carbon::today()->subDays($day);
                $trend = 1 + (59 - $day) * 0.006;
                $weekly = $date->isWeekend() ? 0.6 : 1.0;

                $impressions = (int) round(48 * $weight * $trend * $weekly);
                $views = (int) round($impressions * 0.145);

                ListingStat::updateOrCreate(
                    ['listing_id' => $listing->id, 'date' => $date],
                    [
                        'impressions' => $impressions,
                        'views' => $views,
                        'favorites' => (int) round($views * 0.15),
                        'unlocks' => $day % 4 === 0 ? 1 : 0,
                    ],
                );
            }
        }
    }

    /** @param array<string, Listing> $listings */
    private function unlocks(Company $company, array $listings): void
    {
        $others = Company::query()->where('id', '!=', $company->id)->get();

        if ($others->isEmpty()) {
            return;
        }

        // По одному объявлению каждой соседней компании: иначе в разделе
        // «Мои контакты» колонка «Объявление» пуста у всех строк,
        // и непонятно, откуда контакт вообще взялся
        $titles = [
            'Пряжа хлопковая 30/1, кардная',
            'Бетон товарный М300 с доставкой',
            'Кирпич керамический М150',
            'Профнастил С8 оцинкованный',
            'Мука пшеничная высшего сорта',
        ];

        foreach ($others as $i => $other) {
            if ($other->listings()->exists()) {
                continue;
            }

            $listing = $other->listings()->create([
                'title' => $titles[$i % count($titles)],
                'type' => Listing::TYPE_SUPPLY,
                'status' => Listing::STATUS_ACTIVE,
                'currency' => 'UZS',
                'city_id' => $other->city_id,
                'published_at' => now()->subDays(30),
                'expires_at' => now()->addDays(60),
            ]);

            $listing->slug = Listing::makeSlug($listing->title, $listing->id);
            $listing->save();
        }

        // Контакты, которые открыли мы — на разных стадиях воронки
        $mine = [
            ['status' => 'deal', 'note' => 'Отгрузили 5 т, качество ок', 'days' => 4],
            ['status' => 'negotiating', 'note' => 'Ждём КП до пятницы', 'days' => 7],
            ['status' => 'rejected', 'note' => 'Не возят в Ташкент', 'days' => 10],
            ['status' => 'contacted', 'note' => 'Перезвонить после 15-го', 'days' => 15],
            ['status' => 'new', 'note' => null, 'days' => 1],
        ];

        foreach ($others->take(count($mine)) as $i => $target) {
            ContactUnlock::updateOrCreate(
                ['company_id' => $company->id, 'target_company_id' => $target->id],
                [
                    'listing_id' => $target->listings()->value('id'),
                    'credits_spent' => 1,
                    'status' => $mine[$i]['status'],
                    'note' => $mine[$i]['note'],
                    'created_at' => now()->subDays($mine[$i]['days']),
                ],
            );
        }

        // Кто открыл наши контакты — раздел «Кто мной интересуется»
        $incoming = [
            ['listing' => 'cement', 'minutes' => 18],
            ['listing' => 'gravel', 'minutes' => 1500],
            ['listing' => 'cement', 'minutes' => 3200],
        ];

        foreach ($others->take(count($incoming)) as $i => $source) {
            ContactUnlock::updateOrCreate(
                ['company_id' => $source->id, 'target_company_id' => $company->id],
                [
                    'listing_id' => $listings[$incoming[$i]['listing']]->id,
                    'credits_spent' => 1,
                    'status' => 'new',
                    'created_at' => now()->subMinutes($incoming[$i]['minutes']),
                ],
            );
        }
    }

    /** @param array<string, Listing> $listings */
    private function reviews(Company $company, array $listings): void
    {
        $authors = Company::query()->where('id', '!=', $company->id)->get();

        if ($authors->count() < 2) {
            return;
        }

        Review::updateOrCreate(
            [
                'company_id' => $company->id,
                'author_company_id' => $authors[0]->id,
                'listing_id' => $listings['cement']->id,
            ],
            [
                'rating' => 5,
                'rating_description' => 5,
                'rating_response' => 5,
                'rating_deadlines' => 5,
                'rating_quality' => 5,
                'body' => 'Заказывали 60 тонн М400. Отгрузили день в день, паспорт качества приложили без напоминаний. Работаем дальше.',
                'deal_confirmed' => true,
                'status' => 'published',
                'created_at' => now()->subHours(3),
            ],
        );

        Review::updateOrCreate(
            [
                'company_id' => $company->id,
                'author_company_id' => $authors[1]->id,
                'listing_id' => $listings['gravel']->id,
            ],
            [
                'rating' => 3,
                'rating_description' => 4,
                'rating_response' => 3,
                'rating_deadlines' => 2,
                'rating_quality' => 4,
                'body' => 'Товар нормальный, но доставку задержали на два дня и предупредили постфактум.',
                'deal_confirmed' => false,
                'reply' => 'Приносим извинения, задержка из-за ремонта на карьере. Компенсировали скидкой на следующую партию.',
                'replied_at' => now()->subDays(15),
                'status' => 'published',
                'created_at' => now()->subDays(16),
            ],
        );

        $this->recalculateRating($company);
    }

    private function recalculateRating(Company $company): void
    {
        $reviews = $company->reviews()->get();

        $company->forceFill([
            'rating' => round((float) $reviews->avg('rating'), 1),
            'reviews_count' => $reviews->count(),
        ])->save();
    }

    /** @param array<string, Listing> $listings */
    private function promotions(Company $company, array $listings): void
    {
        $top = PromotionType::query()->where('code', 'category_top')->first();
        $urgent = PromotionType::query()->where('code', 'urgent')->first();

        if ($top !== null) {
            Promotion::updateOrCreate(
                ['listing_id' => $listings['cement']->id, 'promotion_type_id' => $top->id],
                [
                    'company_id' => $company->id,
                    'category_id' => $listings['cement']->category_id,
                    'units_spent' => $top->cost_units,
                    'status' => 'active',
                    'starts_at' => now()->subDays(5),
                    'ends_at' => now()->addDays(2),
                    'impressions_before' => 412,
                    'impressions_after' => 1430,
                ],
            );
        }

        if ($urgent !== null) {
            Promotion::updateOrCreate(
                ['listing_id' => $listings['gravel']->id, 'promotion_type_id' => $urgent->id],
                [
                    'company_id' => $company->id,
                    'category_id' => $listings['gravel']->category_id,
                    'units_spent' => $urgent->cost_units,
                    'status' => 'active',
                    'starts_at' => now()->subDays(3),
                    'ends_at' => now()->addDays(4),
                    'impressions_before' => 318,
                    'impressions_after' => 604,
                ],
            );
        }
    }

    private function payments(Company $company): void
    {
        $card = PaymentMethod::updateOrCreate(
            ['company_id' => $company->id, 'last4' => '4417'],
            [
                'provider' => 'payme',
                'token' => 'demo-token-not-a-card-number',
                'brand' => 'Uzcard',
                'expires' => '09/28',
                'is_default' => true,
            ],
        );

        $history = [
            ['Тариф Business, 1 мес.', 489_000, 'subscription', 2, 'payme'],
            ['Пакет 20 кредитов', 370_000, 'credits', 14, 'click'],
            ['Тариф Business, 1 мес.', 489_000, 'subscription', 32, 'payme'],
            ['Пакет 50 единиц продвижения', 250_000, 'promo_units', 40, 'payme'],
        ];

        foreach ($history as [$description, $amount, $purpose, $daysAgo, $provider]) {
            Payment::updateOrCreate(
                ['company_id' => $company->id, 'description' => $description, 'paid_at' => now()->subDays($daysAgo)->startOfMinute()],
                [
                    'payment_method_id' => $provider === 'payme' ? $card->id : null,
                    'purpose' => $purpose,
                    'amount' => $amount,
                    'currency' => 'UZS',
                    'provider' => $provider,
                    'status' => 'paid',
                ],
            );
        }
    }

    /**
     * Персональные уведомления демо-пользователю.
     *
     * Дублируют часть событий ленты: событие принадлежит компании,
     * уведомление — человеку и имеет состояние прочтения.
     */
    private function notifications(?User $user): void
    {
        if ($user === null) {
            return;
        }

        $rows = [
            ['contact_unlocked', 'success', 'Компания из Самарканда открыла ваш контакт', 'Объявление «Цемент М400 навалом». Это тёплый лид — с вами уже готовы говорить.', '/cabinet/incoming', 18, false],
            ['new_review', 'warning', 'Новый отзыв: 5 звёзд от «Andijon Tekstil»', 'Отгрузили день в день, паспорт качества приложили без напоминаний.', '/cabinet/reviews', 180, false],
            ['listing_expiring', 'danger', 'Объявление «Щебень фр. 5–20» истекает через 3 дня', 'После истечения показы прекращаются. Продлите в один клик.', '/cabinet/listings', 1440, true],
            ['moderation', 'info', 'Объявление «Арматура А500С» отправлено на модерацию', 'Обычно проверка занимает до 2 часов в рабочее время.', '/cabinet/listings?status=moderation', 2880, true],
            ['broadcast', 'info', 'Оплата через Click и Uzum', 'К Payme добавились ещё два способа оплаты в сумах. Автопродление работает по сохранённой карте.', '/news/oplata-click-uzum', 4320, true],
        ];

        foreach ($rows as [$type, $tone, $title, $body, $url, $minutesAgo, $read]) {
            UserNotification::updateOrCreate(
                ['user_id' => $user->id, 'title' => $title],
                [
                    'company_id' => $user->company_id,
                    'type' => $type,
                    'tone' => $tone,
                    'body' => $body,
                    'url' => $url,
                    'is_broadcast' => $type === 'broadcast',
                    'read_at' => $read ? now()->subMinutes($minutesAgo - 10) : null,
                    'created_at' => now()->subMinutes($minutesAgo),
                ],
            );
        }
    }

    private function events(Company $company): void
    {
        $events = [
            ['unlock', 'success', 'Компания из Самарканда открыла ваш контакт по объявлению «Цемент М400»', 18],
            ['review', 'warning', 'Новый отзыв: 5 звёзд от «ТехноСтрой» — «отгрузили в срок»', 180],
            ['promotion', 'info', 'Продвижение «ТОП категории» на объявлении «Цемент М400» истекает через 2 дня', 600],
            ['expiry', 'danger', 'Объявление «Щебень фр. 5–20» истекает через 3 дня — продлите', 1440],
            ['moderation', 'info', 'Объявление «Арматура А500С» отправлено на модерацию', 2880],
        ];

        foreach ($events as [$type, $tone, $message, $minutesAgo]) {
            ActivityEvent::updateOrCreate(
                ['company_id' => $company->id, 'message' => $message],
                [
                    'type' => $type,
                    'tone' => $tone,
                    'created_at' => now()->subMinutes($minutesAgo),
                ],
            );
        }
    }

    private function searchHits(Company $company): void
    {
        $queries = [
            ['цемент м400 ташкент', 842, 164],
            ['цемент оптом', 618, 88],
            ['портландцемент д20', 294, 61],
            ['щебень 5 20 цена', 271, 34],
            ['поддоны бу купить', 148, 22],
        ];

        foreach ($queries as [$query, $impressions, $clicks]) {
            SearchHit::updateOrCreate(
                ['company_id' => $company->id, 'query' => $query, 'date' => Carbon::today()],
                ['impressions' => $impressions, 'clicks' => $clicks],
            );
        }
    }
}
