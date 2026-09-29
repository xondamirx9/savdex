<?php

declare(strict_types=1);

namespace Tests\Feature\Admin;

use App\Models\Company;
use App\Models\Review;
use App\Models\User;
use App\Support\AdminAccess;
use Illuminate\Database\UniqueConstraintViolationException;
use Illuminate\Foundation\Testing\RefreshDatabase;
use PHPUnit\Framework\Attributes\Test;
use Tests\TestCase;

/**
 * Отзывы из админки: правила модели и права. Сам раздел — в админке на
 * Python (tests/test_reviews_admin.py: заведение, правка, удаление,
 * пересчёт рейтинга, загрузка файлом, пара «автор — компания»).
 *
 * Правка нужна безусловно: опечатка по просьбе автора, персональные
 * данные в тексте, клевета. Заведение — для отзывов, собранных вне
 * сайта.
 *
 * Но по отзывам покупатель решает, с кем работать, и заведённый
 * вручную обязан быть отличим от написанного покупателем. Иначе
 * рейтинг перестаёт что-либо значить, и первым это почувствует тот,
 * кто выбрал поставщика по нему.
 */
class ReviewEditingTest extends TestCase
{
    use RefreshDatabase;

    private function admin(string $role): User
    {
        return User::factory()->create([
            'is_admin' => true,
            'admin_role' => $role,
            'status' => 'active',
        ]);
    }

    private function review(array $attrs = []): Review
    {
        return Review::factory()->create($attrs);
    }

    // ── Заведение вручную ───────────────────────────────────────────

    /** Отзыв покупателя пометку не получает. */
    #[Test]
    public function отзыв_покупателя_остаётся_покупательским(): void
    {
        $this->assertSame(Review::ORIGIN_BUYER, $this->review()->origin);
    }

    // ── Доступ к загрузке ───────────────────────────────────────────

    /**
     * Загрузка пачкой двигает рейтинг сильнее, чем месяц работы
     * модератора, — поэтому она отдельное право и не у него.
     */
    #[Test]
    public function загружать_отзывы_файлом_может_не_каждый(): void
    {
        $this->actingAs($this->admin(AdminAccess::SUPERADMIN));
        $this->assertTrue(AdminAccess::allows('reviews.import'));

        $this->actingAs($this->admin(AdminAccess::ADMIN));
        $this->assertTrue(AdminAccess::allows('reviews.import'));

        $this->actingAs($this->admin(AdminAccess::MODERATOR));
        $this->assertFalse(AdminAccess::allows('reviews.import'), 'модератор отзывы файлом не грузит');

        $this->actingAs($this->admin(AdminAccess::CONTENT_MANAGER));
        $this->assertFalse(AdminAccess::allows('reviews.import'));
    }

    // ── Повтор пары ─────────────────────────────────────────────────

    /**
     * Последний рубеж — сама база.
     *
     * Индекс на (компания, автор, объявление) обещал «один отзыв
     * на пару», но у отзыва о компании вообще объявления нет, а NULL
     * в уникальном индексе не равен NULL. Перехват ошибки базы
     * в ReviewService — защита от двойного нажатия — не мог сработать
     * ни разу, потому что ошибки не было.
     */
    #[Test]
    public function база_не_даёт_завести_второй_отзыв_о_компании(): void
    {
        $about = Company::factory()->create();
        $author = Company::factory()->create();

        $this->review([
            'company_id' => $about->id,
            'author_company_id' => $author->id,
            'listing_id' => null,
        ]);

        $this->expectException(UniqueConstraintViolationException::class);

        $this->review([
            'company_id' => $about->id,
            'author_company_id' => $author->id,
            'listing_id' => null,
        ]);
    }
}
