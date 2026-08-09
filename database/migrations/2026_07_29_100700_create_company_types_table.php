<?php

declare(strict_types=1);

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Schema;

/**
 * Типы компаний — справочник вместо константы в коде.
 *
 * Раньше список жил в Company::TYPES: чтобы добавить «Логистика»
 * или «Подрядчик», требовался релиз. Для справочника, который
 * заказчик правит по мере знакомства с рынком, это неоправданно.
 *
 * Названия в отдельной таблице переводов — как у категорий и городов:
 * площадка работает на пяти языках, и колонки name_ru, name_uz…
 * означали бы миграцию при добавлении шестого.
 */
return new class extends Migration
{
    public function up(): void
    {
        Schema::create('company_types', function (Blueprint $table): void {
            $table->id();
            $table->string('code')->unique();
            $table->unsignedSmallInteger('sort')->default(0);
            $table->boolean('is_active')->default(true);
            $table->timestamps();
        });

        Schema::create('company_type_translations', function (Blueprint $table): void {
            $table->id();
            $table->foreignId('company_type_id')->constrained()->cascadeOnDelete();
            $table->string('locale', 5);
            $table->string('name');
            $table->timestamps();

            $table->unique(['company_type_id', 'locale']);
        });

        /*
         * Переносим текущие значения, чтобы уже заведённые компании
         * не остались с типом, которого нет в справочнике.
         */
        $types = [
            'manufacturer' => ['Производитель', 'Ishlab chiqaruvchi', 'Manufacturer', '制造商', 'Üretici'],
            'importer' => ['Импортёр', 'Importchi', 'Importer', '进口商', 'İthalatçı'],
            'distributor' => ['Дистрибьютор', 'Distribyutor', 'Distributor', '经销商', 'Distribütör'],
            'trader' => ['Торговая компания', 'Savdo kompaniyasi', 'Trading company', '贸易公司', 'Ticaret şirketi'],
            'service' => ['Услуги', 'Xizmatlar', 'Services', '服务', 'Hizmetler'],
        ];

        $locales = ['ru', 'uz', 'en', 'zh', 'tr'];
        $now = now();
        $sort = 0;

        foreach ($types as $code => $names) {
            $id = DB::table('company_types')->insertGetId([
                'code' => $code,
                'sort' => $sort++,
                'is_active' => true,
                'created_at' => $now,
                'updated_at' => $now,
            ]);

            foreach ($locales as $i => $locale) {
                DB::table('company_type_translations')->insert([
                    'company_type_id' => $id,
                    'locale' => $locale,
                    'name' => $names[$i],
                    'created_at' => $now,
                    'updated_at' => $now,
                ]);
            }
        }
    }

    public function down(): void
    {
        Schema::dropIfExists('company_type_translations');
        Schema::dropIfExists('company_types');
    }
};
