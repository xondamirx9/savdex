<?php

declare(strict_types=1);

use App\Models\Review;
use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Schema;

/**
 * Откуда взялся отзыв.
 *
 * По отзывам покупатель решает, с кем работать. Пока отзыв мог
 * появиться только от покупателя, вопрос «откуда» не стоял. С правкой
 * и загрузкой из админки он появляется, и без ответа рейтинг перестаёт
 * что-либо значить: нельзя отличить, какая его часть пришла от людей,
 * а какая заведена площадкой.
 *
 * Отсюда же берётся ответственность: у заведённого вручную видно,
 * кто именно его завёл.
 */
return new class extends Migration
{
    public function up(): void
    {
        Schema::table('reviews', function (Blueprint $table): void {
            $table->string('origin')->default(Review::ORIGIN_BUYER)->after('status');

            // Кто завёл или загрузил. У отзывов покупателей пусто
            $table->foreignId('created_by')->nullable()->after('origin')
                ->constrained('users')->nullOnDelete();

            $table->index('origin');
        });

        // Всё, что было до этой правки, пришло от покупателей
        DB::table('reviews')->update(['origin' => Review::ORIGIN_BUYER]);
    }

    public function down(): void
    {
        Schema::table('reviews', function (Blueprint $table): void {
            $table->dropConstrainedForeignId('created_by');
            $table->dropIndex(['origin']);
            $table->dropColumn('origin');
        });
    }
};
