<?php

use App\Models\Review;
use Illuminate\Database\Migrations\Migration;

/**
 * Скрыть отзывы, которые написал демо-сидер, а не люди.
 *
 * CabinetDemoSeeder на каждом деплое с SEED_DEMO=true брал автором
 * отзыва о демо-компании случайную компанию из базы — на живом сайте
 * это настоящие компании. На главной оказывались три одинаковых
 * отзыва «Заказывали 60 тонн М400…» от разных фирм.
 *
 * Отзывы узнаются по тексту сидера дословно. Не удаляются, а
 * скрываются с пометкой модератора: след остаётся, а рейтинг
 * компании пересчитывается (Review::booted).
 */
return new class extends Migration
{
    public const BODIES = [
        'Заказывали 60 тонн М400. Отгрузили день в день, паспорт качества приложили без напоминаний. Работаем дальше.',
        'Товар нормальный, но доставку задержали на два дня и предупредили постфактум.',
    ];

    public function up(): void
    {
        Review::query()
            ->whereIn('body', self::BODIES)
            ->where('status', '!=', Review::STATUS_HIDDEN)
            ->each(fn (Review $review) => $review->forceFill([
                'status' => Review::STATUS_HIDDEN,
                'moderator_note' => 'Скрыт автоматически: демо-отзыв сидера, а не отзыв покупателя.',
                'moderated_at' => now(),
            ])->save());
    }

    public function down(): void
    {
        // Возвращать выдуманные отзывы на витрину незачем
    }
};
