<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

/**
 * Когда владелец в последний раз менял данные компании.
 *
 * Заполненные сведения о компании (название, ИНН, страна, адрес…)
 * меняются раз в полгода — из настроек профиля. Поле держит дату
 * последней такой смены; пусто — менять можно сразу.
 */
return new class extends Migration
{
    public function up(): void
    {
        Schema::table('companies', function (Blueprint $table): void {
            $table->timestamp('profile_changed_at')->nullable();
        });
    }

    public function down(): void
    {
        Schema::table('companies', function (Blueprint $table): void {
            $table->dropColumn('profile_changed_at');
        });
    }
};
