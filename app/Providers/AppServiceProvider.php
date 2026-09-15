<?php

declare(strict_types=1);

namespace App\Providers;

use App\Models\Broadcast;
use App\Models\Category;
use App\Models\Company;
use App\Models\CompanyDocument;
use App\Models\CompanyType;
use App\Models\CreditPack;
use App\Models\ItTask;
use App\Models\LandingBlock;
use App\Models\Listing;
use App\Models\NewsPost;
use App\Models\Page;
use App\Models\Payment;
use App\Models\Plan;
use App\Models\PromoCode;
use App\Models\Review;
use App\Models\Setting;
use App\Models\Subscription;
use App\Models\Tender;
use App\Models\User;
use App\Observers\AuditObserver;
use App\Support\AdminAccess;
use App\Support\Seo;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Gate;
use Illuminate\Support\ServiceProvider;
use Illuminate\Validation\Rules\Password;

class AppServiceProvider extends ServiceProvider
{
    public function register(): void
    {
        /*
         * Мета-теги страницы — один экземпляр на запрос.
         *
         * scoped, а не singleton: между запросами объект жить не должен,
         * иначе на постоянно работающем сервере (Octane) заголовок одной
         * страницы утечёт на следующую.
         */
        $this->app->scoped(Seo::class);
    }

    public function boot(): void
    {
        $this->configurePasswordRules();
        $this->configureModels();
        $this->configureDatabase();
        $this->configureAdminAbilities();
        $this->configureAuditLog();
    }

    /**
     * Единые требования к паролю для всего приложения.
     *
     * Проверка по базе утечек (uncompromised) обращается к внешнему API
     * при каждом вызове. В тестах это давало 77 секунд на 13 проверок
     * и делало прогон зависимым от сети, поэтому вне продакшена она отключена.
     * Требования к длине и составу при этом сохраняются везде.
     */
    private function configurePasswordRules(): void
    {
        Password::defaults(function (): Password {
            $rule = Password::min(10)->letters()->numbers();

            return $this->app->isProduction() ? $rule->uncompromised() : $rule;
        });
    }

    /**
     * Права админ-панели как обычные гейты Laravel.
     *
     * Гейт заводится на каждую пару «раздел + действие», даже на те, что
     * ни одной роли не выданы. Незаведённый гейт возвращает «нет» всем
     * подряд, включая суперадмина, — и такой отказ выглядел бы не ошибкой
     * в списке, а сознательным запретом, что искали бы долго.
     */
    private function configureAdminAbilities(): void
    {
        foreach (AdminAccess::all() as $ability) {
            Gate::define($ability, fn (User $user): bool => $user->hasAdminAbility($ability));
        }
    }

    /**
     * Что попадает в журнал действий автоматически.
     *
     * Карта «модель → раздел прав» держится здесь, а не выводится из
     * имени класса: Page и NewsPost относятся к одному разделу прав,
     * Category и CompanyType — к другому, и никакое правило по имени
     * этого не угадает.
     *
     * Наблюдатель пишет только правки администратора в панели. Решения
     * по существу — одобрение, отзыв прав, возврат средств — пишут сами
     * службы: «изменил поле moderation_status» отвечает не на тот
     * вопрос, ради которого журнал заводят.
     */
    private function configureAuditLog(): void
    {
        $sections = [
            User::class => 'users',
            Company::class => 'companies',
            Listing::class => 'listings',
            Tender::class => 'tenders',
            ItTask::class => 'ittasks',
            CompanyDocument::class => 'documents',
            Review::class => 'reviews',
            Payment::class => 'payments',
            Subscription::class => 'subscriptions',
            Plan::class => 'plans',
            PromoCode::class => 'promocodes',
            CreditPack::class => 'creditpacks',
            Page::class => 'content',
            NewsPost::class => 'content',
            LandingBlock::class => 'content',
            Category::class => 'catalogs',
            CompanyType::class => 'catalogs',
            Broadcast::class => 'broadcasts',
            Setting::class => 'settings',
        ];

        AuditObserver::watch($sections);

        foreach (array_keys($sections) as $model) {
            $model::observe(AuditObserver::class);
        }
    }

    private function configureModels(): void
    {
        // Обращение к незагруженной связи должно падать в разработке,
        // а не тихо порождать N+1 запросов на продакшене (PERF-05 из QA.md).
        Model::preventLazyLoading(! $this->app->isProduction());

        // Присвоение несуществующего атрибута — почти всегда опечатка.
        // На этом уже поймались: email_verified_at молча отбрасывался,
        // потому что не был перечислен в #[Fillable].
        Model::preventSilentlyDiscardingAttributes(! $this->app->isProduction());
    }

    private function configureDatabase(): void
    {
        if (! $this->app->isProduction()) {
            DB::whenQueryingForLongerThan(500, function (): void {
                logger()->warning('Медленный запрос к базе данных: дольше 500 мс');
            });
        }
    }
}
