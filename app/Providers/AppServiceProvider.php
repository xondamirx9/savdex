<?php

declare(strict_types=1);

namespace App\Providers;

use App\Support\Seo;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Support\Facades\DB;
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
