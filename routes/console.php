<?php

declare(strict_types=1);

use App\Jobs\TranslateListing;
use App\Jobs\TranslateNewsPost;
use App\Jobs\TranslateResume;
use App\Jobs\TranslateTender;
use App\Models\AudienceView;
use App\Models\Listing;
use App\Models\NewsPost;
use App\Models\Resume;
use App\Models\Tender;
use App\Services\MachineTranslator;
use App\Services\Payments\PaymentGatewayManager;
use App\Services\Payments\UzumGateway;
use App\Support\CurrencyRate;
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

// Снятие истёкших объявлений (listings:expire) ведёт Django — хозяин
// таблицы listings с этапа 4 (python/manage.py expire_listings, цикл в
// docker/render-entrypoint.sh, те же 06:00). Сама команда осталась:
// ею сверяется Python-версия (python/tests/test_listing_expiry.py)

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

// Просьбы оставить отзыв — днём по Ташкенту, а не ночью: уведомление
// в колокольчике читают, когда человек на площадке (AskForReviews)
Schedule::command('reviews:ask')
    ->dailyAt('06:00')
    ->withoutOverlapping()
    ->onOneServer();

/*
 * Курсы ЦБ — заранее, а не первым посетителем: кэш живёт сутки,
 * и без обновления по расписанию тот, кто откроет каталог сразу
 * после его истечения, ждал бы ответа cbu.uz до пяти секунд.
 * Каждые четыре часа: ЦБ публикует курс раз в день, но в какой час —
 * не обещает.
 */
Schedule::call(fn () => app(CurrencyRate::class)->refresh())
    ->everyFourHours()
    ->name('cbu-rates:refresh')
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
 * лимиты переводчика), опубликованные до появления функции и
 * переведённые руками не на все языки — из книги или в админке.
 * Небольшими порциями — переводчик внешний и бесплатный.
 */
Schedule::call(function (): void {
    if (! config('services.machine_translation.enabled')) {
        return;
    }

    Listing::query()
        ->where('status', Listing::STATUS_ACTIVE)
        ->lackingTranslations()
        ->orderBy('id')
        ->limit(20)
        ->pluck('id')
        ->each(fn (int $id) => TranslateListing::dispatch($id));
})->hourly()->name('listings-translate-catchup')->onOneServer();

// Резюме — по той же схеме: должность, текст о себе и места работы
Schedule::call(function (): void {
    if (! config('services.machine_translation.enabled')) {
        return;
    }

    Resume::query()
        ->where('status', Resume::STATUS_PUBLISHED)
        ->lackingTranslations()
        ->orderBy('id')
        ->limit(10)
        ->pluck('id')
        ->each(fn (int $id) => TranslateResume::dispatch($id));
})->hourly()->name('resumes-translate-catchup')->onOneServer();

// Тендеры переводятся по той же схеме, что объявления
Schedule::call(function (): void {
    if (! config('services.machine_translation.enabled')) {
        return;
    }

    Tender::query()
        ->where('status', Tender::STATUS_PUBLISHED)
        // По ключам языков, а не сравнением с '[]': json-столбец
        // PostgreSQL со строкой не сравнивает, и добор падал
        ->where(function ($q): void {
            foreach (MachineTranslator::TARGETS as $locale) {
                $q->orWhereJsonDoesntContainKey('title_i18n->'.$locale);
            }
        })
        ->orderBy('id')
        ->limit(20)
        ->pluck('id')
        ->each(fn (int $id) => TranslateTender::dispatch($id));
})->hourly()->name('tenders-translate-catchup')->onOneServer();

/*
 * Новости — по той же схеме, что объявления и тендеры, но каждые пять
 * минут, а не раз в час. С этапа 2 переноса новости правит админка на
 * Python: она не ставит перевод в очередь сама, а сбрасывает перевод
 * изменённого поля, и этот добор — единственный путь к переводу.
 * Раз в час значило бы до часа русского текста на всех языках.
 */
Schedule::call(function (): void {
    if (! config('services.machine_translation.enabled')) {
        return;
    }

    NewsPost::query()
        ->where('is_published', true)
        ->lackingTranslations()
        ->orderBy('id')
        ->limit(20)
        ->pluck('id')
        ->each(fn (int $id) => TranslateNewsPost::dispatch($id));
})->everyFiveMinutes()->name('news-translate-catchup')->onOneServer();

/*
 * Перевод прочего текста из базы — описаний компаний, IT-задач,
 * отзывов, услуг продвижения (App\Support\ContentTranslation).
 * Каждую минуту: страница ставит текст в очередь при первом показе,
 * и перевод должен успеть к следующему заходу, а не через час.
 */
Schedule::command('translations:fill --limit=20')
    ->everyMinute()
    ->withoutOverlapping()
    ->onOneServer();

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
