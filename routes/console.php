<?php

declare(strict_types=1);

use App\Jobs\TranslateListing;
use App\Jobs\TranslateNewsPost;
use App\Jobs\TranslateResume;
use App\Jobs\TranslateTender;
use App\Models\Listing;
use App\Models\NewsPost;
use App\Models\Resume;
use App\Models\Tender;
use App\Services\MachineTranslator;
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
// таблицы listings с этапа 4 (python/savdex/schedule.py, цикл в
// docker/render-entrypoint.sh, те же 06:00). Сама команда осталась:
// ею сверяется Python-версия (python/tests/test_listing_expiry.py)

// Завершение продвижений (promotions:finish, каждый час) и расчётные
// периоды (billing:reset-periods, 00:30) ведёт Django — хозяин таблиц денег
// с шага 72 (python/savdex/payments/periods.py, задачи promotions_finish и
// billing_reset_periods в python/savdex/schedule.py). Команды остались:
// ими сверяется Python-версия (python/tests/test_billing_periods.py)

// Пересчёт рейтингов (ratings:recalculate, 03:00) ведёт Django — хозяин
// companies с этапа 5 (python/savdex/schedule.py). Команда осталась:
// ею сверяется Python-версия (python/tests/test_schedule.py)

// Просьбы оставить отзыв (reviews:ask, 06:00) ведёт Django — хозяин
// user_notifications с этапа 5 (python/savdex/schedule.py). Команда
// осталась: ею сверяется Python-версия (python/tests/test_review_ask.py)

// Курсы ЦБ заранее, каждые четыре часа (cbu-rates:refresh), ведёт Django
// (python/savdex/web/currency.py, задача cbu_rates): тот же кэш, тот же формат

// Экспорты и импорты Filament уходят в очередь; на проде нужен
// постоянный воркер, но раз в час подбираем зависшие задания
Schedule::command('queue:prune-batches --hours=48')->daily();
Schedule::command('queue:prune-failed --hours=336')->weekly();

// Чистку «Кто смотрел» (audience-views:prune, старше 90 дней) ведёт
// Django — хозяин audience_views с этапа 5 (python/savdex/schedule.py)

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

// Прозвон Uzum Checkout (uzum-probe, каждый час) ведёт Django — задача
// uzum_probe в python/savdex/schedule.py; итог — в журнал контейнера
