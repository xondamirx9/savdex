<?php

declare(strict_types=1);

namespace Database\Seeders;

use App\Models\City;
use App\Models\Company;
use App\Models\CompanyContact;
use App\Models\Country;
use App\Models\User;
use Illuminate\Database\Seeder;
use Illuminate\Support\Facades\DB;

/**
 * Демонстрационные данные для локальной проверки.
 *
 * Не путать с боевым наполнением: это ровно то, что нужно, чтобы
 * пройти сценарии руками — несколько компаний с контактами разного
 * типа, проверенные и непроверенные, из разных городов.
 */
class DemoSeeder extends Seeder
{
    public function run(): void
    {
        // Код в нижнем регистре — как в GeoSeeder. С 'UZ' поиск
        // не находил существующую страну и заводил её дубль
        $uz = Country::firstOrCreate(
            ['code' => 'uz'],
            ['phone_code' => '998', 'currency_code' => 'UZS', 'sort' => 1, 'is_active' => true],
        );

        // Без перевода Country::name() отдаёт код страны, и на визитке
        // вместо «Узбекистан» показывается «UZ»
        $uz->translations()->firstOrCreate(['locale' => 'ru'], ['name' => 'Узбекистан']);
        $uz->translations()->firstOrCreate(['locale' => 'uz'], ['name' => 'Oʻzbekiston']);
        $uz->translations()->firstOrCreate(['locale' => 'en'], ['name' => 'Uzbekistan']);

        // Названия городов лежат в city_translations — по одному на язык,
        // поэтому создаём город и сразу русский перевод к нему
        $cities = collect([
            'Ташкент' => 'tashkent',
            'Самарканд' => 'samarkand',
            'Фергана' => 'fergana',
            'Бекабад' => 'bekabad',
        ])->mapWithKeys(function (string $slug, string $name) use ($uz): array {
            $city = City::firstOrCreate(
                ['country_id' => $uz->id, 'slug' => $slug],
                ['is_active' => true],
            );

            $city->translations()->firstOrCreate(['locale' => 'ru'], ['name' => $name]);

            return [$name => $city];
        });

        /*
         * Только очевидно вымышленные компании: без ИНН, без бейджей
         * верификации, без истории сделок и отзывов. Демо-данные,
         * похожие на реальные юрлица с «историей», — репутационный
         * и правовой риск, даже на стенде (аудит 29.08.2026, п. 2.2).
         */
        $companies = [
            [
                'name' => 'ООО «Демо-Поставщик»',
                'city' => 'Ташкент',
                'type' => 'distributor',
                'description' => 'Демонстрационная карточка поставщика для проверки сценариев. Не является реальной компанией.',
                'founded_year' => 2020,
                'employees_range' => '10-50',
                'verification_level' => Company::VERIFICATION_NONE,
                'contacts' => [
                    ['phone', '+998 00 000-00-01', 'Отдел продаж', 'Демо Контакт'],
                    ['email', 'demo-supplier@example.com', 'Коммерческие предложения', null],
                ],
            ],
            [
                'name' => 'ООО «Демо-Закупщик»',
                'city' => 'Самарканд',
                'type' => 'trader',
                'primary_role' => 'buyer',
                'description' => 'Демонстрационная карточка закупщика для проверки сценариев. Не является реальной компанией.',
                'founded_year' => 2022,
                'employees_range' => '1-10',
                'verification_level' => Company::VERIFICATION_NONE,
                'contacts' => [
                    ['phone', '+998 00 000-00-02', 'Отдел снабжения', null],
                    ['email', 'demo-buyer@example.com', null, null],
                ],
            ],
        ];

        DB::transaction(function () use ($companies, $uz, $cities): void {
            foreach ($companies as $data) {
                $contacts = $data['contacts'];
                unset($data['contacts']);

                $city = $cities[$data['city']];
                unset($data['city']);

                $company = Company::firstOrCreate(
                    ['name' => $data['name']],
                    [...$data, 'country_id' => $uz->id, 'city_id' => $city->id],
                );

                foreach ($contacts as $i => [$type, $value, $label, $person]) {
                    CompanyContact::firstOrCreate(
                        ['company_id' => $company->id, 'type' => $type, 'value' => $value],
                        [
                            'label' => $label,
                            'contact_person' => $person,
                            'is_primary' => $i === 0,
                            'is_public' => true,
                            'sort_order' => $i,
                        ],
                    );
                }

                if (filled($company->website)) {
                    CompanyContact::firstOrCreate(
                        ['company_id' => $company->id, 'type' => CompanyContact::TYPE_WEBSITE, 'value' => $company->website],
                        ['is_primary' => true, 'is_public' => true, 'sort_order' => 90],
                    );
                }
            }

            // Тестовая учётная запись для проверки кабинета
            $demo = User::firstOrCreate(
                ['email' => 'demo@savdex.uz'],
                [
                    'name' => 'Демо Пользователь',
                    'phone' => '+998 00 000-00-01',
                    // Пароль из окружения: в репозитории его быть не должно,
                    // даже для демо — файл попадает в бэкапы и в чужие копии
                    'password' => env('DEMO_PASSWORD', 'ChangeMe-2026!'),
                    'locale' => 'ru',
                    'company_role' => User::ROLE_OWNER,
                    'email_verified_at' => now(),
                    'status' => 'active',
                ],
            );

            $demo->company_id ??= Company::where('name', 'ООО «Демо-Поставщик»')->value('id');
            $demo->save();
        });

        $this->command?->info('Демо-данные готовы. Вход: demo@savdex.uz, пароль из DEMO_PASSWORD.');
    }
}
