<?php

declare(strict_types=1);

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Schema;

/**
 * Пометка об источнике данных на визитке компании.
 *
 * Карточки, заведённые площадкой из открытых источников (реестры,
 * каталоги), обязаны об этом говорить: посетитель должен понимать,
 * что профиль ещё не подтверждён самой компанией. Текст пометки
 * правится в админке по каждой компании; пустое поле скрывает блок.
 *
 * Бэкфилл: пометку получают компании без единого сотрудника —
 * ровно те, кого заводила площадка, а не сами владельцы.
 */
return new class extends Migration
{
    private const NOTE = 'Данные компании взяты из открытых источников. Если это ваша компания — зарегистрируйтесь и напишите в поддержку, чтобы подтвердить профиль и управлять им.';

    public function up(): void
    {
        Schema::table('companies', function (Blueprint $table): void {
            $table->string('source_note', 500)->nullable()->after('description');
        });

        DB::table('companies')
            ->whereNull('deleted_at')
            ->whereNotExists(fn ($q) => $q->selectRaw('1')
                ->from('users')
                ->whereColumn('users.company_id', 'companies.id'))
            ->update(['source_note' => self::NOTE]);
    }

    public function down(): void
    {
        Schema::table('companies', function (Blueprint $table): void {
            $table->dropColumn('source_note');
        });
    }
};
