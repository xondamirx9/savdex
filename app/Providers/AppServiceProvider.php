<?php

declare(strict_types=1);

namespace App\Providers;

use App\Models\Broadcast;
use App\Models\Category;
use App\Models\City;
use App\Models\Company;
use App\Models\CompanyDocument;
use App\Models\CompanyType;
use App\Models\Country;
use App\Models\CreditPack;
use App\Models\Crm\Communication;
use App\Models\Crm\Contact;
use App\Models\Crm\Deal;
use App\Models\Crm\Lead;
use App\Models\Crm\Task;
use App\Models\ItTask;
use App\Models\LandingBlock;
use App\Models\Listing;
use App\Models\NewsPost;
use App\Models\Page;
use App\Models\Payment;
use App\Models\Plan;
use App\Models\PromoCode;
use App\Models\Refund;
use App\Models\Review;
use App\Models\Setting;
use App\Models\Subscription;
use App\Models\Support\Ticket;
use App\Models\Tender;
use App\Models\User;
use App\Observers\AuditObserver;
use App\Support\AdminAccess;
use App\Support\CurrencyRate;
use App\Support\PriceDisplay;
use App\Support\Runtime;
use App\Support\Seo;
use Illuminate\Database\Connection;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Events\QueryExecuted;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Gate;
use Illuminate\Support\ServiceProvider;
use Illuminate\Support\Str;
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

        // Курсы и валюта языка запоминаются на запрос: по обращению
        // на карточку — это десятки походов в кэш за одной таблицей
        $this->app->scoped(CurrencyRate::class);
        $this->app->scoped(PriceDisplay::class);
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

            // Проверка по базе утечек нужна везде, где пароли заводят
            // живые люди, — то есть на любом развёрнутом сайте, а не
            // только там, где окружение названо production
            return Runtime::isDeployed($this->app->environment())
                ? $rule->uncompromised()
                : $rule;
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
            Lead::class => 'leads',
            Deal::class => 'deals',
            Contact::class => 'contacts',
            Task::class => 'tasks',
            Communication::class => 'communications',
            Ticket::class => 'support',
            Refund::class => 'refunds',
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
            Country::class => 'catalogs',
            City::class => 'catalogs',
            Broadcast::class => 'broadcasts',
            Setting::class => 'settings',
        ];

        AuditObserver::watch($sections);

        foreach (array_keys($sections) as $model) {
            $model::observe(AuditObserver::class);
        }
    }

    /**
     * Предохранители разработки — только на машине разработчика.
     *
     * Условием было «не production», и площадка с APP_ENV=staging
     * получала их в полном составе: страница нарочно падала у живого
     * посетителя там, где должна была просто отработать. Одно слово
     * в настройке хостинга решало, ломается сайт или нет.
     *
     * Runtime задаёт вопрос правильно: не «как называется окружение»,
     * а «смотрит ли на него кто-то живой».
     */
    private function configureModels(): void
    {
        $developing = Runtime::isDeveloperMachine($this->app->environment());

        // Обращение к незагруженной связи должно падать в разработке,
        // а не тихо порождать N+1 запросов на боевом сайте (PERF-05 из QA.md).
        Model::preventLazyLoading($developing);

        // Присвоение несуществующего атрибута — почти всегда опечатка.
        // На этом уже поймались: email_verified_at молча отбрасывался,
        // потому что не был перечислен в #[Fillable].
        Model::preventSilentlyDiscardingAttributes($developing);
    }

    /**
     * Сигнал о медленной странице — с подробностями и на боевом сайте тоже.
     *
     * Прежняя версия писала «что-то было медленным» и молчала о том,
     * что именно. По такому сообщению причину не найти: остаётся
     * гадать, а гадание стоит дороже самой починки.
     *
     * Работает и в продакшене намеренно. Медленно отвечающая панель —
     * это как раз то, что замечают на живом сайте и не замечают на
     * машине разработчика с базой под боком.
     */
    private function configureDatabase(): void
    {
        /*
         * Число запросов отличает «один тяжёлый» от «четырёхсот мелких».
         * Без него полсекунды одинаково выглядят и в том, и в другом
         * случае, а чинятся они совершенно по-разному.
         */
        $queries = 0;

        DB::listen(static function () use (&$queries): void {
            $queries++;
        });

        DB::whenQueryingForLongerThan(500, function (Connection $connection, QueryExecuted $query) use (&$queries): void {
            logger()->warning('База отвечает медленно', [
                'всего_мс' => (int) round($connection->totalQueryDuration()),
                'запросов' => $queries,
                // Запрос, на котором счётчик перевалил за порог. Не
                // обязательно самый медленный, но почти всегда он
                'на_запросе' => Str::limit(preg_replace('/\s+/', ' ', $query->sql) ?? '', 400),
                'этот_мс' => (int) round($query->time),
                'страница' => $this->app->runningInConsole()
                    ? 'консоль: '.implode(' ', array_slice($_SERVER['argv'] ?? [], 1))
                    : request()->method().' '.request()->path(),
            ]);
        });
    }
}
