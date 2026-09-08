<?php

declare(strict_types=1);

use App\Jobs\TranslateListing;
use App\Jobs\TranslateTender;
use App\Models\AudienceView;
use App\Models\Listing;
use App\Models\Tender;
use App\Services\Payments\PaymentGatewayManager;
use App\Services\Payments\UzumGateway;
use Illuminate\Support\Facades\Log;
use Illuminate\Support\Facades\Schedule;

/*
|--------------------------------------------------------------------------
| Задачи по расписанию
|--------------------------------------------------------------------------
|
| На сервере нужен один cron-вход:
|     * * * * * cd /path && php artisan schedule:run >> /dev/null 2>&1
|
| Без него объявления не истекают, продвижения занимают места вечно,
| месячные лимиты не обнуляются, а рейтинг остаётся нулевым у всех.
| Это не оптимизация, а условие работы продукта.
*/

// Раньше рабочего дня: человек утром видит, что объявление истекает,
// и успевает продлить до того, как оно пропадёт из выдачи
Schedule::command('listings:expire')
    ->dailyAt('06:00')
    ->withoutOverlapping()
    ->onOneServer();

/*
 * Каждый час, а не раз в сутки: слоты «ТОП категории» и «ТОП главной»
 * ограничены, и сутки простоя занятого места — это сутки, которые
 * никто не может купить.
 */
Schedule::command('promotions:finish')
    ->hourly()
    ->withoutOverlapping()
    ->onOneServer();

Schedule::command('billing:reset-periods')
    ->dailyAt('00:30')
    ->withoutOverlapping()
    ->onOneServer();

// Рейтинг байесовский и зависит от среднего по площадке: он меняется
// у всех, когда появляются новые отзывы, поэтому считается целиком
Schedule::command('ratings:recalculate')
    ->dailyAt('03:00')
    ->withoutOverlapping()
    ->onOneServer();

// Экспорты и импорты Filament уходят в очередь; на проде нужен
// постоянный воркер, но раз в час подбираем зависшие задания
Schedule::command('queue:prune-batches --hours=48')->daily();
Schedule::command('queue:prune-failed --hours=336')->weekly();

// «Кто смотрел» полезен свежим: кабинет показывает месяц, ещё два
// держим про запас, старше — просто занимает место в базе
Schedule::call(fn () => AudienceView::query()
    ->where('created_at', '<', now()->subDays(90))
    ->delete())
    ->name('audience-views:prune')
    ->dailyAt('04:00')
    ->onOneServer();

/*
 * Добор переводов объявлений: несложившиеся при публикации (сеть,
 * лимиты переводчика) и опубликованные до появления функции.
 * Небольшими порциями — переводчик внешний и бесплатный.
 */
Schedule::call(function (): void {
    if (! config('services.machine_translation.enabled')) {
        return;
    }

    Listing::query()
        ->where('status', Listing::STATUS_ACTIVE)
        ->where(fn ($q) => $q
            ->whereNull('title_i18n')
            ->orWhereIn('title_i18n', ['[]', '{}']))
        ->orderBy('id')
        ->limit(20)
        ->pluck('id')
        ->each(fn (int $id) => TranslateListing::dispatch($id));
})->hourly()->name('listings-translate-catchup')->onOneServer();

// Тендеры переводятся по той же схеме, что объявления
Schedule::call(function (): void {
    if (! config('services.machine_translation.enabled')) {
        return;
    }

    Tender::query()
        ->where('status', Tender::STATUS_PUBLISHED)
        ->where(fn ($q) => $q->whereNull('title_i18n')
            ->orWhereIn('title_i18n', ['[]', '{}']))
        ->orderBy('id')
        ->limit(20)
        ->pluck('id')
        ->each(fn (int $id) => TranslateTender::dispatch($id));
})->hourly()->name('tenders-translate-catchup')->onOneServer();

/*
 * Прозвон Uzum Checkout: доступен ли API с нашего адреса (прямо или
 * через прокси со статическим IP) и приняты ли ключи. Касса при сбое
 * молча откатывается на оплату по счёту, и без проверки об упавшем
 * прокси или отозванном ключе узнали бы по отсутствию платежей.
 * Запись в лог — LOG_CHANNEL=stderr, то есть видно в логах Render.
 */
Schedule::call(function (): void {
    if (! config('payments.providers.uzum.enabled') || ! config('payments.providers.uzum.checkout')) {
        return;
    }

    $gateway = app(PaymentGatewayManager::class)->for('uzum');

    if (! $gateway instanceof UzumGateway) {
        return;
    }

    $result = $gateway->probe();

    if ($result['ok']) {
        Log::info('payment.uzum.probe_ok', ['message' => $result['message']]);
    } else {
        Log::error('payment.uzum.probe_failed', ['message' => $result['message']]);
    }
})->hourly()->name('uzum-probe')->onOneServer();
