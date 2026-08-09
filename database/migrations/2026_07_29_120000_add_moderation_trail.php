<?php

declare(strict_types=1);

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

/**
 * След решения модератора: кто, когда и с какой формулировкой.
 *
 * Обращения — споры по отзывам, жалобы на контакты, документы —
 * хранили только сторону заявителя. Решение записывалось одним
 * словом в статус, без автора и без объяснения. Через месяц на
 * вопрос «почему сняли мой отзыв» ответить было нечем, а по жалобам
 * с возвратом кредита это ещё и денежная операция без основания.
 *
 * moderated_by с nullOnDelete: увольнение модератора не должно
 * стирать историю его решений.
 */
return new class extends Migration
{
    public function up(): void
    {
        Schema::table('reviews', function (Blueprint $table): void {
            $table->text('moderator_note')->nullable()->after('dispute_reason');
            $table->foreignId('moderated_by')->nullable()->after('moderator_note')->constrained('users')->nullOnDelete();
            $table->timestamp('moderated_at')->nullable()->after('moderated_by');

            // Очередь споров открывается по этому индексу
            $table->index('dispute_status');
        });

        Schema::table('contact_unlocks', function (Blueprint $table): void {
            $table->text('moderator_note')->nullable()->after('complaint_reason');
            $table->foreignId('moderated_by')->nullable()->after('moderator_note')->constrained('users')->nullOnDelete();
            $table->timestamp('moderated_at')->nullable()->after('moderated_by');

            $table->index('complaint_status');
        });

        Schema::table('company_documents', function (Blueprint $table): void {
            $table->foreignId('moderated_by')->nullable()->after('moderation_note')->constrained('users')->nullOnDelete();
            $table->timestamp('moderated_at')->nullable()->after('moderated_by');
        });
    }

    public function down(): void
    {
        Schema::table('reviews', function (Blueprint $table): void {
            $table->dropIndex(['dispute_status']);
            $table->dropConstrainedForeignId('moderated_by');
            $table->dropColumn(['moderator_note', 'moderated_at']);
        });

        Schema::table('contact_unlocks', function (Blueprint $table): void {
            $table->dropIndex(['complaint_status']);
            $table->dropConstrainedForeignId('moderated_by');
            $table->dropColumn(['moderator_note', 'moderated_at']);
        });

        Schema::table('company_documents', function (Blueprint $table): void {
            $table->dropConstrainedForeignId('moderated_by');
            $table->dropColumn('moderated_at');
        });
    }
};
