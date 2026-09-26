<?php

/*
 * Наполнение проверочной базы для сравнения выгрузок PHP и Python.
 *
 * Запускает tests/test_export_parity.py после migrate:fresh. Фабрики —
 * где они есть, прямые вставки — где нет, и крайние случаи, на которых
 * две реализации могли бы разойтись:
 *
 *   - JSON с экранированной кириллицей (так пишет json_encode по умолчанию)
 *     и JSON с «неровными» пробелами — PHP отдаёт его сырым текстом, и
 *     Python обязан сделать то же. Без этих двух строк сравнение
 *     проходило и с ошибкой: проверено;
 *   - текст длиннее предела ячейки Excel — обрезка с пометкой;
 *   - ИНН и телефоны с ведущими нулями — остаются строками;
 *   - удалённые записи — выгружаются намеренно;
 *   - пустые значения, логические поля, дробные координаты.
 *
 * Не код площадки: живёт рядом с тестами Python и Laravel не трогает.
 */

use App\Models\Category;
use App\Models\Company;
use App\Models\ContactUnlock;
use App\Models\Listing;
use App\Models\Review;
use App\Models\Tender;
use App\Models\User;
use Illuminate\Contracts\Console\Kernel;
use Illuminate\Support\Facades\DB;

$root = dirname(__DIR__, 3);

require $root.'/vendor/autoload.php';
$app = require $root.'/bootstrap/app.php';
$app->make(Kernel::class)->bootstrap();

mt_srand(42);
fake()->seed(42);

$plan = DB::table('plans')->value('id');
$cats = Category::query()->pluck('id')->all();

$companies = Company::factory()->count(12)->create();
$companies->each(function (Company $c, int $i) use ($plan, $cats) {
    User::factory()->count(1 + $i % 3)->create(['company_id' => $c->id]);
    Listing::factory()->count($i % 4)->create(['company_id' => $c->id]);
    DB::table('wallets')->insert(['company_id' => $c->id, 'credits' => $i * 3, 'created_at' => now(), 'updated_at' => now()]);
    DB::table('subscriptions')->insert(['company_id' => $c->id, 'plan_id' => $plan, 'started_at' => now()->subDays($i), 'created_at' => now(), 'updated_at' => now()]);
    DB::table('company_contacts')->insert(['company_id' => $c->id, 'type' => 'phone', 'value' => '00998'.str_pad((string) $i, 7, '0', STR_PAD_LEFT), 'created_at' => now(), 'updated_at' => now()]);
    DB::table('company_attributes')->insert(['company_id' => $c->id, 'key' => 'сертификат', 'value' => 'ISO 900'.$i, 'created_at' => now(), 'updated_at' => now()]);
    if ($cats) {
        DB::table('company_category')->insert(['company_id' => $c->id, 'category_id' => $cats[$i % count($cats)]]);
    }
    DB::table('company_documents')->insert(['company_id' => $c->id, 'type' => 'license', 'title' => 'Лицензия №'.$i, 'file_path' => "documents/{$c->id}/l.pdf", 'created_at' => now(), 'updated_at' => now()]);
});

Tender::factory()->count(4)->create();

$listings = Listing::query()->get();
foreach ($listings as $n => $l) {
    DB::table('listing_images')->insert(['listing_id' => $l->id, 'path' => "listings/{$l->id}/a.webp", 'created_at' => now(), 'updated_at' => now()]);
    DB::table('listing_attributes')->insert(['listing_id' => $l->id, 'key' => 'Марка', 'value' => 'М'.(400 + $n), 'created_at' => now(), 'updated_at' => now()]);
    foreach (range(0, 2) as $d) {
        DB::table('listing_stats')->insert(['listing_id' => $l->id, 'date' => now()->subDays($d)->toDateString(), 'views' => $n + $d, 'created_at' => now(), 'updated_at' => now()]);
    }
}
$u = User::query()->first();
foreach ($listings->take(3) as $l) {
    DB::table('favorites')->insert(['user_id' => $u->id, 'listing_id' => $l->id, 'created_at' => now(), 'updated_at' => now()]);
}

// Раскрытия и отзывы — между разными компаниями
foreach (range(1, 4) as $i) {
    $unlock = ContactUnlock::factory()->create(['company_id' => $companies[$i]->id, 'target_company_id' => $companies[0]->id]);
    Review::factory()->create(['company_id' => $companies[0]->id, 'author_company_id' => $companies[$i]->id, 'listing_id' => null]);
}

// ── Крайние случаи ──
$edge = $companies[1];
DB::table('companies')->where('id', $edge->id)->update([
    'description' => str_repeat('Длинное описание. ', 2500),          // > 32000 знаков — обрезка
    'lat' => 41.3110810, 'lng' => 69.2405620,
    'tin' => '000123456',                                                 // ведущие нули
    'it_specializations' => json_encode(['веб', 'мобильные/приложения']), // экранированный \u и \/
]);
DB::table('companies')->where('id', $companies[2]->id)->update(['deleted_at' => now()->subDay()]); // удалённая
DB::table('companies')->where('id', $companies[3]->id)->update([
    'it_specializations' => '["сырой текст",  "с пробелами"]',              // json, записанный не через json_encode
    'website' => null, 'phone' => null,
]);
$admin = User::query()->where('company_id', $companies[4]->id)->first();
DB::table('users')->where('id', $admin->id)->update(['is_admin' => true, 'admin_role' => 'superadmin', 'admin_permissions' => json_encode(['reports' => ['view', 'export']])]);
if ($l = Listing::query()->first()) {
    DB::table('listings')->where('id', $l->id)->update([
        'tags' => json_encode(['цемент', 'М400'], JSON_UNESCAPED_UNICODE),
        'title_i18n' => json_encode(['en' => 'Cement', 'uz' => 'Sement']),
        'deleted_at' => now(),
    ]);
}

// JSON в том виде, в каком его пишет Laravel (\u-экранирование),
// и в произвольном: оба должны попасть в выгрузку как есть
$alive = Listing::query()->whereNull('deleted_at')->orderBy('id')->limit(2)->pluck('id');
DB::table('listings')->where('id', $alive[0])->update(['tags' => json_encode(['цемент', 'М400'])]);
DB::table('listings')->where('id', $alive[1])->update(['title_i18n' => '{"en":  "Cement \\/ bags",   "uz": "Sement"}']);

foreach (['companies', 'users', 'company_contacts', 'company_category', 'company_documents', 'wallets', 'subscriptions', 'company_attributes', 'contact_unlocks', 'reviews', 'listings', 'listing_images', 'listing_attributes', 'listing_stats', 'favorites', 'tenders'] as $t) {
    printf("%-20s %d\n", $t, DB::table($t)->count());
}
