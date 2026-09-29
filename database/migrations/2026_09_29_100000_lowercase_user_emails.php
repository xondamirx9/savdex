<?php

declare(strict_types=1);

use Illuminate\Database\Migrations\Migration;
use Illuminate\Support\Facades\DB;

/**
 * Почта пользователей — в нижний регистр.
 *
 * Вход ищет адрес в нижнем регистре; учётки с заглавными буквами в почте
 * (заведённые до нормализации при регистрации или поправленные в админке)
 * не находились, и человек с верным паролем видел «неверный пароль».
 *
 * Адрес, который после приведения совпал бы с другой учёткой, не
 * трогается: сливать две учётки молча нельзя, такие разбираются руками.
 * Вход их всё равно находит — он ищет без учёта регистра.
 */
return new class extends Migration
{
    public function up(): void
    {
        DB::table('users')
            ->whereRaw('email <> lower(email)')
            ->orderBy('id')
            ->get(['id', 'email'])
            ->each(function (object $user): void {
                $lower = mb_strtolower(trim((string) $user->email));

                $taken = DB::table('users')
                    ->where('id', '!=', $user->id)
                    ->whereRaw('lower(email) = ?', [$lower])
                    ->exists();

                if (! $taken) {
                    DB::table('users')->where('id', $user->id)->update(['email' => $lower]);
                }
            });
    }

    public function down(): void
    {
        // Исходный регистр не сохранялся — и возвращать его незачем
    }
};
