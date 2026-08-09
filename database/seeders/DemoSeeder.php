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

        $companies = [
            [
                'name' => 'ООО «Стройбаза»',
                'legal_name' => 'Общество с ограниченной ответственностью «Стройбаза»',
                'tin' => '304561278',
                'city' => 'Ташкент',
                'type' => 'distributor',
                'address' => 'г. Ташкент, Мирзо-Улугбекский р-н, ул. Мустакиллик, 42',
                'website' => 'stroybaza.uz',
                'description' => 'Поставляем строительные материалы напрямую с заводов Узбекистана с 2016 года. Собственный склад 4 000 м² в Ташкенте, автопарк из 12 единиц техники.',
                'founded_year' => 2016,
                'employees_range' => '50-100',
                'verification_level' => Company::VERIFICATION_COMPANY,
                'rating' => 4.8,
                'reviews_count' => 34,
                'completed_deals_count' => 47,
                'response_time_hours' => 2,
                'contacts' => [
                    ['phone', '+998 90 123-45-67', 'Отдел продаж', 'Рустам Каримов'],
                    ['phone', '+998 71 200-45-80', 'Склад и отгрузка', null],
                    ['email', 'sales@stroybaza.uz', 'Коммерческие предложения', null],
                    ['email', 'buhgalteriya@stroybaza.uz', 'Бухгалтерия и документы', null],
                ],
            ],
            [
                'name' => '«Andijon Tekstil»',
                'legal_name' => 'ЧП «Andijon Tekstil»',
                'tin' => '301882940',
                'city' => 'Фергана',
                'type' => 'manufacturer',
                'address' => 'Ферганская область, г. Фергана, ул. Мустакиллик, 7',
                'website' => 'andijon-tekstil.uz',
                'description' => 'Производство хлопковой пряжи и тканей. Экспорт в Турцию, Китай и Россию с 2019 года.',
                'founded_year' => 2019,
                'employees_range' => '100+',
                'verification_level' => Company::VERIFICATION_EXTENDED,
                'rating' => 4.9,
                'reviews_count' => 61,
                'completed_deals_count' => 112,
                'response_time_hours' => 1,
                'contacts' => [
                    ['phone', '+998 90 555-11-22', 'Экспортный отдел', 'Азиз Ганиев'],
                    ['email', 'export@andijon-tekstil.uz', 'Экспорт', null],
                ],
            ],
            [
                'name' => '«ТехноСтрой»',
                'legal_name' => 'ООО «ТехноСтрой»',
                'tin' => '309442156',
                'city' => 'Ташкент',
                'type' => 'trading',
                'primary_role' => 'buyer',
                'address' => 'г. Ташкент, Чиланзарский р-н, ул. Бунёдкор, 15',
                'description' => 'Строительная компания. Закупаем материалы для собственных объектов.',
                'founded_year' => 2020,
                'employees_range' => '10-50',
                'verification_level' => Company::VERIFICATION_COMPANY,
                'rating' => 4.6,
                'reviews_count' => 18,
                'completed_deals_count' => 23,
                'response_time_hours' => 5,
                'contacts' => [
                    ['phone', '+998 71 244-00-11', 'Отдел снабжения', null],
                    ['email', 'zakupki@technostroy.uz', null, null],
                ],
            ],
            [
                'name' => '«Uzmetkombinat Savdo»',
                'legal_name' => 'АО «Uzmetkombinat Savdo»',
                'tin' => '200145772',
                'city' => 'Бекабад',
                'type' => 'manufacturer',
                'address' => 'Ташкентская область, г. Бекабад, ул. Металлургов, 1',
                'website' => 'uzmk-savdo.uz',
                'description' => 'Торговый дом металлургического комбината. Арматура, прокат, трубы.',
                'founded_year' => 2012,
                'employees_range' => '100+',
                'verification_level' => Company::VERIFICATION_EXTENDED,
                'rating' => 4.9,
                'reviews_count' => 88,
                'completed_deals_count' => 204,
                'response_time_hours' => 3,
                'contacts' => [
                    ['phone', '+998 70 779-00-00', 'Сбыт', null],
                    ['email', 'sale@uzmk-savdo.uz', null, null],
                ],
            ],
            [
                'name' => "«G'isht Konsern»",
                'tin' => null,
                'city' => 'Самарканд',
                'type' => 'manufacturer',
                'description' => 'Производство керамического кирпича.',
                'founded_year' => 2024,
                'employees_range' => '10-50',
                'verification_level' => Company::VERIFICATION_NONE,
                'rating' => 4.1,
                'reviews_count' => 5,
                'completed_deals_count' => 4,
                'response_time_hours' => 18,
                'contacts' => [
                    ['phone', '+998 66 233-77-88', null, null],
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
                    'name' => 'Рустам Каримов',
                    'phone' => '+998 90 123-45-67',
                    // Пароль из окружения: в репозитории его быть не должно,
                    // даже для демо — файл попадает в бэкапы и в чужие копии
                    'password' => env('DEMO_PASSWORD', 'ChangeMe-2026!'),
                    'locale' => 'ru',
                    'company_role' => User::ROLE_OWNER,
                    'email_verified_at' => now(),
                    'status' => 'active',
                ],
            );

            $demo->company_id ??= Company::where('name', 'ООО «Стройбаза»')->value('id');
            $demo->save();
        });

        $this->command?->info('Демо-данные готовы. Вход: demo@savdex.uz, пароль из DEMO_PASSWORD.');
    }
}
