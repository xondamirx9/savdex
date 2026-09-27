<?php

use App\Models\Company;
use App\Models\Promotion;
use App\Services\ReviewService;
use Illuminate\Database\Migrations\Migration;
use Illuminate\Support\Facades\DB;

/**
 * Скрыть демо-наполнение, попавшее в живую базу.
 *
 * До 15.09 боевая служба жила с SEED_DEMO=true и APP_ENV=staging, и
 * демо-сидеры (DemoSeeder, CabinetDemoSeeder, ItTasksDemoSeeder) на
 * каждом деплое писали в живую базу выдуманные компании, объявления,
 * платежи — и не только к своим компаниям: заявки на закупку и
 * объявления «от имени» настоящих компаний, раскрытия их контактов.
 *
 * Ничего настоящего не трогаем:
 * - демо-компания узнаётся по имени из сидеров (всех их версий) или
 *   по пометке IT-демо, и только если в ней не зарегистрировался ни
 *   один настоящий человек — компания с тем же именем, но живыми
 *   сотрудниками, остаётся как есть;
 * - у настоящих компаний скрываются только объявления сидера — по
 *   дословному заголовку (у «соседских» ещё и без описания: форма
 *   без описания объявление не сохранит);
 * - удаляются только раскрытия контактов без сотрудника (user_id):
 *   их писал сидер, настоящее раскрытие всегда делает человек.
 *
 * Скрывается, а не удаляется: компания — блокировкой с причиной,
 * объявления и задачи — в архив, платежи — «Отменён» с пометкой,
 * отзывы — «Скрыт». След остаётся, витрина и отчёты — чистые.
 */
return new class extends Migration
{
    /** Демо-компании всех версий сидеров. */
    private const COMPANIES = [
        // DemoSeeder до аудита 29.08
        'ООО «Стройбаза»', '«Andijon Tekstil»', '«ТехноСтрой»', '«Uzmetkombinat Savdo»',
        // DemoSeeder после аудита
        'ООО «Демо-Поставщик»', 'ООО «Демо-Закупщик»',
        // ItTasksDemoSeeder
        'IT-студия «Digital Plov»', 'ООО «Tashkent Soft»', 'ООО «Samarkand Dev»',
        'ООО «Андижан текстиль»', 'АО «Ферганский цемент»', 'ООО «Навоий агро экспорт»', 'ООО «Бухара упаковка»',
    ];

    private const IT_NOTE = 'Демонстрационная компания раздела «IT-услуги».';

    private const DEMO_EMAILS = ['demo@savdex.uz'];

    /** CabinetDemoSeeder::requests — заявки «от имени» настоящих компаний. */
    private const REQUESTS = [
        'Закупаем цемент М400, 200 т в месяц',
        'Требуется профлист оцинкованный С8, 5 000 м²',
        'Ищем поставщика хлопковой пряжи 30/1',
        'Нужен щебень фракции 5–20, регулярно',
        'Закупка муки пшеничной высшего сорта, 50 т',
    ];

    /** CabinetDemoSeeder::unlocks — объявления «соседям» без объявлений. */
    private const NEIGHBOUR_LISTINGS = [
        'Пряжа хлопковая 30/1, кардная',
        'Бетон товарный М300 с доставкой',
        'Кирпич керамический М150',
        'Профнастил С8 оцинкованный',
        'Мука пшеничная высшего сорта',
    ];

    private const REASON = 'Демонстрационные данные: скрыты с витрины.';

    public function up(): void
    {
        $now = now();
        $companies = DB::table('companies')
            ->where(fn ($q) => $q->whereIn('name', self::COMPANIES)->orWhere('source_note', self::IT_NOTE))
            ->whereNotExists(fn ($q) => $q->selectRaw('1')->from('users')
                ->whereColumn('users.company_id', 'companies.id')
                ->whereNotIn('users.email', self::DEMO_EMAILS))
            ->pluck('id')
            ->all();

        DB::transaction(function () use ($companies, $now): void {
            DB::table('companies')->whereIn('id', $companies)->where('status', '!=', Company::STATUS_BLOCKED)
                ->update(['status' => Company::STATUS_BLOCKED, 'blocked_reason' => self::REASON, 'blocked_at' => $now, 'updated_at' => $now]);

            $live = ['active', 'moderation', 'needs_changes', 'draft'];

            DB::table('listings')->whereIn('company_id', $companies)->whereIn('status', $live)
                ->update(['status' => 'archived', 'updated_at' => $now]);

            DB::table('listings')->where('type', 'demand')->whereIn('title', self::REQUESTS)->whereIn('status', $live)
                ->update(['status' => 'archived', 'updated_at' => $now]);

            DB::table('listings')->where('type', 'supply')->whereNull('description')
                ->whereIn('title', self::NEIGHBOUR_LISTINGS)->whereIn('status', $live)
                ->update(['status' => 'archived', 'updated_at' => $now]);

            DB::table('it_tasks')->whereIn('company_id', $companies)->where('status', 'active')
                ->update(['status' => 'archived', 'updated_at' => $now]);

            DB::table('contact_unlocks')->whereNull('user_id')
                ->where(fn ($q) => $q->whereIn('company_id', $companies)->orWhereIn('target_company_id', $companies))
                ->delete();

            DB::table('payments')->whereIn('company_id', $companies)->where('status', 'paid')
                ->update(['status' => 'failed', 'admin_note' => 'Демо-платёж сидера — не настоящие деньги.', 'updated_at' => $now]);

            DB::table('subscriptions')->whereIn('company_id', $companies)->where('status', 'active')
                ->update(['status' => 'expired', 'ends_at' => $now, 'updated_at' => $now]);

            // Через модель: она обнуляет active_key, иначе место продвижения занято навсегда
            Promotion::query()->whereIn('company_id', $companies)->where('status', 'active')
                ->each(fn (Promotion $p) => $p->forceFill(['status' => 'finished'])->save());

            DB::table('reviews')
                ->where(fn ($q) => $q->whereIn('company_id', $companies)->orWhereIn('author_company_id', $companies))
                ->where('status', '!=', 'hidden')
                ->update(['status' => 'hidden', 'moderator_note' => self::REASON, 'moderated_at' => $now, 'updated_at' => $now]);

            DB::table('users')->whereIn('email', self::DEMO_EMAILS)->where('status', 'active')
                ->update(['status' => 'blocked', 'updated_at' => $now]);
        });

        // Отзывы от демо-компаний могли стоять у настоящих — их рейтинг без них
        $reviewed = DB::table('reviews')->whereIn('author_company_id', $companies)->distinct()->pluck('company_id');

        foreach (Company::query()->whereIn('id', $reviewed)->get() as $company) {
            app(ReviewService::class)->recalculate($company);
        }
    }

    public function down(): void
    {
        // Возвращать демо на живую витрину незачем
    }
};
