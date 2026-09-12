<?php

declare(strict_types=1);

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

/**
 * Выполненные IT-задачи: результат (ссылка на сайт, что сделано) и
 * исполнитель. Витрина показывает их отдельной вкладкой — как портфолио
 * раздела: заказчик видит, что здесь реально делают, исполнитель —
 * что его работа останется на виду.
 */
return new class extends Migration
{
    public function up(): void
    {
        Schema::table('it_tasks', function (Blueprint $table): void {
            $table->foreignId('contractor_company_id')->nullable()->after('user_id')
                ->constrained('companies')->nullOnDelete();
            $table->string('result_url')->nullable()->after('closed_at');
            $table->text('result_summary')->nullable()->after('result_url');
            $table->timestamp('completed_at')->nullable()->after('result_summary');
        });
    }

    public function down(): void
    {
        Schema::table('it_tasks', function (Blueprint $table): void {
            $table->dropConstrainedForeignId('contractor_company_id');
            $table->dropColumn(['result_url', 'result_summary', 'completed_at']);
        });
    }
};
