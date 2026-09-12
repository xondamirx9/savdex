<?php

declare(strict_types=1);

namespace Database\Seeders;

use App\Models\Company;
use App\Models\ItTask;
use Illuminate\Database\Seeder;

/**
 * Демо-наполнение раздела «IT-услуги»: открытые задачи от компаний
 * и выполненные — с ссылкой на результат и исполнителем.
 *
 * Пустой раздел не объясняет, зачем он: заказчик не понимает, что
 * сюда можно принести, исполнитель — что здесь есть работа.
 * Идемпотентен: компании ищутся по названию, задачи — по заголовку,
 * повторный запуск обновляет, а не дублирует.
 */
class ItTasksDemoSeeder extends Seeder
{
    public function run(): void
    {
        if (app()->isProduction()) {
            $this->command?->error('Демо-данные на боевом сервере не создаются.');

            return;
        }

        $contractors = $this->contractors();
        $customers = $this->customers();

        foreach ($this->openTasks() as $i => $task) {
            $this->upsert($task, $customers[$i % count($customers)], null, [
                'status' => ItTask::STATUS_ACTIVE,
                'published_at' => now()->subDays($task['days_ago']),
                'deadline_at' => now()->addDays($task['deadline_in']),
                'responses_count' => $task['responses'],
                'views_count' => $task['responses'] * 17 + 40,
            ]);
        }

        foreach ($this->completedTasks() as $i => $task) {
            $this->upsert($task, $customers[$i % count($customers)], $contractors[$i % count($contractors)], [
                'status' => ItTask::STATUS_COMPLETED,
                'published_at' => now()->subDays($task['days_ago'] + 45),
                'deadline_at' => now()->subDays($task['days_ago'] + 5),
                'closed_at' => now()->subDays($task['days_ago']),
                'completed_at' => now()->subDays($task['days_ago']),
                'result_url' => $task['result_url'],
                'result_summary' => $task['result_summary'],
                'responses_count' => $task['responses'],
                'views_count' => $task['responses'] * 23 + 120,
            ]);
        }
    }

    /**
     * @param  array<string, mixed>  $task
     * @param  array<string, mixed>  $extra
     */
    private function upsert(array $task, Company $customer, ?Company $contractor, array $extra): void
    {
        $record = ItTask::query()->firstOrNew(['title' => $task['title']]);

        $record->fill([
            'company_id' => $customer->id,
            'contractor_company_id' => $contractor?->id,
            'description' => $task['description'],
            'service_type' => $task['service_type'],
            'stack' => $task['stack'],
            'budget_type' => $task['budget_type'],
            'budget_from' => $task['budget_from'] ?? null,
            'budget_to' => $task['budget_to'] ?? null,
            'currency' => 'UZS',
        ]);

        $record->forceFill($extra)->save();
    }

    // ── Компании ─────────────────────────────────────────────

    /** @return list<Company> */
    private function contractors(): array
    {
        $rows = [
            ['name' => 'IT-студия «Digital Plov»', 'specs' => ['web', 'design', 'integration'],
                'description' => 'Веб-студия из Ташкента: интернет-магазины, корпоративные сайты, интеграции с 1С и платёжными системами. 9 лет, 140+ проектов.'],
            ['name' => 'ООО «Tashkent Soft»', 'specs' => ['mobile', 'automation', 'integration'],
                'description' => 'Мобильные приложения для iOS и Android, Telegram-боты, автоматизация продаж и складского учёта.'],
            ['name' => 'ООО «Samarkand Dev»', 'specs' => ['erp', 'support', 'automation'],
                'description' => 'Внедрение и доработка 1С, ERP для производств, техническая поддержка инфраструктуры.'],
        ];

        return array_map(fn (array $row): Company => tap(
            Company::query()->firstOrNew(['name' => $row['name']]),
            function (Company $company) use ($row): void {
                $company->fill([
                    'type' => 'service',
                    'primary_role' => 'supplier',
                    'description' => $row['description'],
                    'is_it_provider' => true,
                    'it_specializations' => $row['specs'],
                    'status' => 'active',
                    'source_note' => 'Демонстрационная компания раздела «IT-услуги».',
                ])->save();
            },
        ), $rows);
    }

    /** @return list<Company> */
    private function customers(): array
    {
        $rows = [
            ['name' => 'ООО «Андижан текстиль»', 'type' => 'manufacturer', 'description' => 'Производство трикотажного полотна и пряжи, экспорт в Россию и Турцию.'],
            ['name' => 'АО «Ферганский цемент»', 'type' => 'manufacturer', 'description' => 'Цемент М400 и М500, отгрузка навалом и в мешках со склада завода.'],
            ['name' => 'ООО «Навоий агро экспорт»', 'type' => 'trader', 'description' => 'Экспорт сухофруктов и орехов, собственная сортировка и упаковка.'],
            ['name' => 'ООО «Бухара упаковка»', 'type' => 'manufacturer', 'description' => 'Гофрокартон, стретч-плёнка, упаковка под заказ для пищевых производств.'],
        ];

        return array_map(fn (array $row): Company => tap(
            Company::query()->firstOrNew(['name' => $row['name']]),
            function (Company $company) use ($row): void {
                $company->fill([
                    'type' => $row['type'],
                    'primary_role' => 'both',
                    'description' => $row['description'],
                    'status' => 'active',
                    'source_note' => 'Демонстрационная компания раздела «IT-услуги».',
                ])->save();
            },
        ), $rows);
    }

    // ── Задачи ───────────────────────────────────────────────

    /** @return list<array<string, mixed>> */
    private function openTasks(): array
    {
        return [
            [
                'title' => 'Интернет-магазин трикотажа с оптовыми ценами и оплатой картой',
                'description' => "Нужен интернет-магазин для оптовых и розничных покупателей: каталог с размерными сетками, два уровня цен (розница и опт от 50 единиц), корзина, оплата Uzum/Payme, интеграция с 1С по остаткам.\n\nЕсть логотип и фирменные цвета, фото товаров сделаем сами. Хостинг и домен уже куплены.\n\nВажно: сайт на трёх языках — русский, узбекский, английский.",
                'service_type' => 'web', 'stack' => ['Laravel', 'React', 'Payme', 'Uzum', '1С'],
                'budget_type' => 'range', 'budget_from' => 35_000_000, 'budget_to' => 60_000_000,
                'days_ago' => 1, 'deadline_in' => 60, 'responses' => 4,
            ],
            [
                'title' => 'Telegram-бот для приёма заявок дилеров и уведомлений об отгрузке',
                'description' => "Дилеры сейчас пишут менеджерам в личку — заявки теряются. Нужен бот: дилер выбирает марку цемента, объём, дату, бот создаёт заявку и уведомляет отдел продаж. После отгрузки дилер получает уведомление с номером машины.\n\nАдминка для менеджеров — можно в виде веб-страницы. Хранить заявки в базе, экспорт в Excel.",
                'service_type' => 'automation', 'stack' => ['Telegram Bot API', 'Python', 'PostgreSQL'],
                'budget_type' => 'fixed', 'budget_from' => 12_000_000,
                'days_ago' => 2, 'deadline_in' => 30, 'responses' => 7,
            ],
            [
                'title' => 'Мобильное приложение для торговых представителей с офлайн-режимом',
                'description' => "Торговые представители объезжают точки и принимают заказы. Нужно приложение под Android: каталог с ценами, остатки, оформление заказа, работа без интернета с последующей синхронизацией, геометки визитов.\n\nБэкенд — наш 1С:УТ 11, есть REST-интерфейс. Нужно 15 лицензий, iOS пока не нужен.",
                'service_type' => 'mobile', 'stack' => ['Kotlin', 'Android', '1С', 'REST'],
                'budget_type' => 'range', 'budget_from' => 50_000_000, 'budget_to' => 90_000_000,
                'days_ago' => 4, 'deadline_in' => 90, 'responses' => 3,
            ],
            [
                'title' => 'Внедрение 1С:УНФ и перенос учёта из Excel',
                'description' => "Небольшое производство упаковки, 40 сотрудников. Учёт заказов, сырья и готовой продукции ведётся в Excel — пора переходить в 1С:УНФ.\n\nНужно: установка, настройка под наш процесс (заказ → раскрой → печать → отгрузка), перенос справочников и остатков, обучение трёх сотрудников. Лицензии купим сами.",
                'service_type' => 'erp', 'stack' => ['1С:УНФ'],
                'budget_type' => 'negotiable',
                'days_ago' => 6, 'deadline_in' => 45, 'responses' => 5,
            ],
            [
                'title' => 'Редизайн корпоративного сайта экспортёра сухофруктов на английском',
                'description' => "Текущий сайт сделан в 2018 году и не открывается нормально с телефона. Нужен современный сайт-визитка для иностранных покупателей: продукция с фото и спецификациями, сертификаты, форма запроса прайса, страница «О компании» с видео с производства.\n\nЯзыки: английский (основной), русский, китайский. Контент подготовим, нужны дизайн и вёрстка.",
                'service_type' => 'design', 'stack' => ['Figma', 'WordPress'],
                'budget_type' => 'range', 'budget_from' => 15_000_000, 'budget_to' => 25_000_000,
                'days_ago' => 8, 'deadline_in' => 40, 'responses' => 6,
            ],
            [
                'title' => 'Интеграция сайта с 1С и службами доставки (BTS, Fargo)',
                'description' => "Есть интернет-магазин на Laravel и 1С:Розница. Нужно: автоматическая выгрузка остатков и цен из 1С на сайт каждые 15 минут, заказы с сайта — в 1С, статусы доставки из BTS и Fargo — покупателю в SMS.\n\nДоступ к коду сайта и 1С дадим. Ждём исполнителя с опытом похожих интеграций — приложите примеры.",
                'service_type' => 'integration', 'stack' => ['Laravel', '1С', 'REST', 'SMS'],
                'budget_type' => 'fixed', 'budget_from' => 18_000_000,
                'days_ago' => 11, 'deadline_in' => 25, 'responses' => 2,
            ],
        ];
    }

    /** @return list<array<string, mixed>> */
    private function completedTasks(): array
    {
        return [
            [
                'title' => 'Оптовый интернет-магазин пряжи с личным кабинетом дилера',
                'description' => 'Нужен был B2B-магазин пряжи: каталог по составу и номеру, цены по группам клиентов, личный кабинет дилера с историей заказов и документами, синхронизация с 1С.',
                'service_type' => 'web', 'stack' => ['Laravel', 'Vue', '1С'],
                'budget_type' => 'range', 'budget_from' => 40_000_000, 'budget_to' => 55_000_000,
                'days_ago' => 12, 'responses' => 9,
                'result_url' => 'https://andijan-yarn.uz',
                'result_summary' => 'Запущен магазин с 1 200 позициями и тремя уровнями цен. Дилеры оформляют заказы сами — нагрузка на отдел продаж снизилась вдвое, остатки обновляются из 1С каждые 10 минут.',
            ],
            [
                'title' => 'Бот заказа цемента для дилеров в Telegram',
                'description' => 'Приём заявок дилеров через Telegram с подтверждением менеджером, уведомления об отгрузке и номере машины, отчёт за день в Excel.',
                'service_type' => 'automation', 'stack' => ['Telegram Bot API', 'Node.js', 'PostgreSQL'],
                'budget_type' => 'fixed', 'budget_from' => 9_500_000,
                'days_ago' => 20, 'responses' => 11,
                'result_url' => 'https://t.me/fercement_bot',
                'result_summary' => 'Бот принимает 60–80 заявок в день, менеджеры подтверждают их одной кнопкой. Заявки перестали теряться, время оформления сократилось с 15 минут до 2.',
            ],
            [
                'title' => 'Приложение сборщика заказов для склада сухофруктов',
                'description' => 'Android-приложение для сборщиков: сканирование штрихкодов, чек-лист по заказу, взвешивание, печать этикеток, обмен с 1С.',
                'service_type' => 'mobile', 'stack' => ['Kotlin', 'Android', '1С', 'Zebra'],
                'budget_type' => 'range', 'budget_from' => 45_000_000, 'budget_to' => 70_000_000,
                'days_ago' => 33, 'responses' => 5,
                'result_url' => 'https://play.google.com/store/apps/details?id=uz.navoiagro.picker',
                'result_summary' => 'Сборка заказа по сканеру вместо бумажных листов: ошибки комплектации упали на 90%, приложение работает на 12 терминалах Zebra.',
            ],
            [
                'title' => 'Переход с Excel на 1С:УНФ для производства упаковки',
                'description' => 'Внедрение 1С:УНФ: заказы, раскрой, учёт сырья и готовой продукции, перенос остатков, обучение сотрудников.',
                'service_type' => 'erp', 'stack' => ['1С:УНФ'],
                'budget_type' => 'negotiable',
                'days_ago' => 41, 'responses' => 4,
                'result_url' => null,
                'result_summary' => 'Перенесли справочники и остатки за две недели, настроили производственный цикл под процесс заказчика. Три сотрудника прошли обучение, Excel выключен с первого числа.',
            ],
            [
                'title' => 'Корпоративный сайт экспортёра текстиля на трёх языках',
                'description' => 'Сайт-каталог для иностранных покупателей: продукция, сертификаты, запрос прайса, английский, русский и турецкий.',
                'service_type' => 'design', 'stack' => ['Figma', 'Next.js'],
                'budget_type' => 'range', 'budget_from' => 18_000_000, 'budget_to' => 24_000_000,
                'days_ago' => 55, 'responses' => 8,
                'result_url' => 'https://andijantextile.com',
                'result_summary' => 'Дизайн в Figma, вёрстка на Next.js, 3 языка. Через месяц после запуска — 14 запросов прайса от покупателей из Турции и Польши.',
            ],
            [
                'title' => 'Обмен остатками и заказами между сайтом и 1С:Розница',
                'description' => 'Двусторонняя интеграция магазина на Laravel с 1С:Розница, статусы доставки покупателю по SMS.',
                'service_type' => 'integration', 'stack' => ['Laravel', '1С', 'REST', 'Eskiz SMS'],
                'budget_type' => 'fixed', 'budget_from' => 16_000_000,
                'days_ago' => 70, 'responses' => 6,
                'result_url' => 'https://buxoro-pack.uz',
                'result_summary' => 'Остатки и цены обновляются каждые 15 минут, заказы попадают в 1С без ручного ввода, покупатели получают SMS о статусе доставки.',
            ],
        ];
    }
}
