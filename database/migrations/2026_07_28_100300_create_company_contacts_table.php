<?php

declare(strict_types=1);

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Schema;

/**
 * Несколько контактов у компании.
 *
 * В таблице companies поля phone / email / telegram / whatsapp одиночные.
 * У реального оптовика это не работает: отдел продаж, склад, бухгалтерия
 * и руководитель — разные номера, и звонить по вопросу отгрузки главному
 * бухгалтеру бессмысленно. Выносим контакты в отдельную таблицу с типом
 * и подписью, кто это.
 *
 * Одиночные поля в companies остаются как «основной контакт» — по ним
 * идёт поиск и они переносятся сюда при первом сохранении профиля.
 */
return new class extends Migration
{
    public function up(): void
    {
        Schema::create('company_contacts', function (Blueprint $table): void {
            $table->id();
            $table->foreignId('company_id')->constrained()->cascadeOnDelete();

            // phone | email | telegram | whatsapp | website
            $table->string('type', 20);

            $table->string('value');

            // «Отдел продаж», «Склад в Ташкенте», «Бухгалтерия»
            $table->string('label')->nullable();

            // ФИО ответственного — часто важнее самого номера
            $table->string('contact_person')->nullable();

            // Основной контакт своего типа: показывается первым,
            // используется в карточках объявлений и при экспорте
            $table->boolean('is_primary')->default(false);

            // Скрытые контакты видны только владельцу компании:
            // например, прямой номер директора не для всех
            $table->boolean('is_public')->default(true);

            $table->unsignedSmallInteger('sort_order')->default(0);

            $table->timestamps();

            $table->index(['company_id', 'type', 'sort_order']);

            // Дубли одного и того же номера внутри компании не нужны
            $table->unique(['company_id', 'type', 'value']);
        });

        // Переносим уже заполненные одиночные контакты, чтобы данные
        // не пропали при переходе на новую структуру
        $this->migrateExistingContacts();
    }

    private function migrateExistingContacts(): void
    {
        $map = [
            'phone' => 'phone',
            'email' => 'email',
            'telegram' => 'telegram',
            'whatsapp' => 'whatsapp',
            'website' => 'website',
        ];

        DB::table('companies')
            ->select(['id', 'phone', 'email', 'telegram', 'whatsapp', 'website', 'contact_person', 'created_at'])
            ->orderBy('id')
            ->chunkById(200, function ($companies) use ($map): void {
                $rows = [];

                foreach ($companies as $company) {
                    foreach ($map as $column => $type) {
                        if (blank($company->{$column})) {
                            continue;
                        }

                        $rows[] = [
                            'company_id' => $company->id,
                            'type' => $type,
                            'value' => $company->{$column},
                            'label' => null,
                            'contact_person' => $type === 'phone' ? $company->contact_person : null,
                            'is_primary' => true,
                            'is_public' => true,
                            'sort_order' => 0,
                            'created_at' => $company->created_at ?? now(),
                            'updated_at' => now(),
                        ];
                    }
                }

                if ($rows !== []) {
                    DB::table('company_contacts')->insert($rows);
                }
            });
    }

    public function down(): void
    {
        Schema::dropIfExists('company_contacts');
    }
};
