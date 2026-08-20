<?php

declare(strict_types=1);

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

/**
 * Промокоды на бесплатный период тарифа.
 *
 * Код одноразовый и именной: активация записывается прямо в строку кода,
 * отдельной таблицы погашений нет — при «один код = одна активация»
 * она хранила бы ровно те же данные во второй раз.
 *
 * Тариф и срок хранятся в самом коде, а не в настройках: акции живут
 * параллельно (месяц Premium партнёрам, две недели Business с выставки),
 * и общий параметр пришлось бы менять перед каждой раздачей.
 */
return new class extends Migration
{
    public function up(): void
    {
        Schema::create('promo_codes', function (Blueprint $table): void {
            $table->id();

            // Код набирают руками с листовки: регистр не важен,
            // хранится в верхнем, сравнение идёт по нему же
            $table->string('code', 32)->unique();

            $table->foreignId('plan_id')->constrained()->cascadeOnDelete();
            $table->unsignedSmallInteger('days');

            /*
             * Срок, до которого код можно активировать. Пустой — бессрочный:
             * коды для точечной выдачи партнёру живут, пока их не погасят.
             */
            $table->timestamp('expires_at')->nullable();

            // Выключенный код не активируется, но остаётся в истории:
            // удалять погашенный код значит терять, кому он достался
            $table->boolean('is_active')->default(true);

            // Для кого выпущен — видно в админке рядом с кодом
            $table->string('note')->nullable();

            $table->timestamp('used_at')->nullable();

            /*
             * Уникальность компании среди погашенных кодов — страховка
             * от гонки: две одновременные активации разных кодов одной
             * компанией иначе прошли бы обе проверки. NULL в уникальном
             * индексе не конфликтуют, поэтому непогашенные коды свободны.
             */
            $table->foreignId('used_by_company_id')->nullable()->unique()->constrained('companies')->nullOnDelete();
            $table->foreignId('used_by_user_id')->nullable()->constrained('users')->nullOnDelete();
            $table->foreignId('subscription_id')->nullable()->constrained()->nullOnDelete();

            $table->foreignId('created_by')->nullable()->constrained('users')->nullOnDelete();
            $table->timestamps();

            // Списки в админке всегда фильтруются по «погашен / свободен»
            $table->index(['used_at', 'is_active']);
        });
    }

    public function down(): void
    {
        Schema::dropIfExists('promo_codes');
    }
};
