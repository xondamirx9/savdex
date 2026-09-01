<?php

declare(strict_types=1);

use Illuminate\Database\Migrations\Migration;
use Illuminate\Support\Facades\DB;

/**
 * Короткая пометка об источнике: без призыва регистрироваться.
 *
 * Обновляются только строки со стандартным текстом — пометки,
 * переписанные в админке руками, не трогаются.
 */
return new class extends Migration
{
    private const OLD = 'Данные компании взяты из открытых источников. Если это ваша компания — зарегистрируйтесь и напишите в поддержку, чтобы подтвердить профиль и управлять им.';

    private const NEW = 'Данные компании взяты из открытых источников.';

    public function up(): void
    {
        DB::table('companies')->where('source_note', self::OLD)->update(['source_note' => self::NEW]);
    }

    public function down(): void
    {
        DB::table('companies')->where('source_note', self::NEW)->update(['source_note' => self::OLD]);
    }
};
