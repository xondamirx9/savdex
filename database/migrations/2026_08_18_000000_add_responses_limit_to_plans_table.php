<?php

declare(strict_types=1);

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

/**
 * Лимит откликов в тарифе.
 *
 * Пока витринный: показывается в карточках тарифов, механика списания
 * подключится, когда появятся сами отклики. null — без ограничений,
 * как у остальных лимитов.
 */
return new class extends Migration
{
    public function up(): void
    {
        Schema::table('plans', function (Blueprint $table): void {
            $table->unsignedInteger('responses_limit')->nullable()->after('contacts_limit');
        });
    }

    public function down(): void
    {
        Schema::table('plans', function (Blueprint $table): void {
            $table->dropColumn('responses_limit');
        });
    }
};
