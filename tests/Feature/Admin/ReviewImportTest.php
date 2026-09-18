<?php

declare(strict_types=1);

namespace Tests\Feature\Admin;

use App\Filament\Imports\ReviewImporter;
use App\Models\Company;
use App\Models\Review;
use App\Models\User;
use App\Support\AdminAccess;
use Filament\Actions\Imports\Models\Import;
use Illuminate\Foundation\Testing\RefreshDatabase;
use PHPUnit\Framework\Attributes\Test;
use Tests\TestCase;

/**
 * Загрузка отзывов файлом.
 *
 * Файл на триста строк двигает рейтинг сильнее, чем месяц работы
 * модератора, поэтому проверяется не «загрузилось», а что именно
 * загрузилось и что при этом не потерялось.
 */
class ReviewImportTest extends TestCase
{
    use RefreshDatabase;

    /** Одна строка файла, пропущенная через импортёр. */
    private function importRow(array $data): ?Review
    {
        $importer = new ReviewImporter(
            import: new Import,
            columnMap: [],
            options: [],
        );

        // Импортёр читает строку из своего $data — так его зовёт Filament
        (function () use ($data): void {
            $this->data = $data;
            $this->originalData = $data;
        })->call($importer);

        $record = $importer->resolveRecord();

        if ($record === null) {
            return null;
        }

        $record->fill([
            'rating' => $data['rating'] ?? null,
            'body' => $data['body'] ?? null,
            'reply' => $data['reply'] ?? null,
        ]);
        $record->save();

        return $record;
    }

    private function company(string $name): Company
    {
        return Company::factory()->create(['name' => $name]);
    }

    // ── Что загружается ─────────────────────────────────────────────

    #[Test]
    public function строка_превращается_в_отзыв(): void
    {
        $this->actingAs(User::factory()->create(['is_admin' => true, 'admin_role' => AdminAccess::ADMIN]));

        $this->company('Oltin Mebel');
        $this->company('Stroy Invest');

        $review = $this->importRow([
            'company' => 'Oltin Mebel',
            'author_company' => 'Stroy Invest',
            'rating' => 5,
            'body' => 'Отгрузили вовремя, качество соответствует описанию.',
        ]);

        $this->assertNotNull($review);
        $this->assertSame(5, $review->rating);
        $this->assertSame(Review::ORIGIN_IMPORT, $review->origin, 'загруженное обязано быть отличимо');
    }

    /** Название в файле написано иначе, чем в справочнике, — не повод терять строку. */
    #[Test]
    public function компания_ищется_без_учёта_регистра_и_пробелов(): void
    {
        $this->company('Oltin Mebel');
        $this->company('Stroy Invest');

        $review = $this->importRow([
            'company' => '  OLTIN MEBEL ',
            'author_company' => 'stroy invest',
            'rating' => 4,
            'body' => 'Работали дважды, оба раза без нареканий.',
        ]);

        $this->assertNotNull($review);
    }

    /**
     * Отзыв о несуществующей компании не заводится.
     *
     * Завести его хуже, чем не завести: он повис бы ни на ком
     * и попал в рейтинг никого.
     */
    #[Test]
    public function незнакомая_компания_пропускается(): void
    {
        $this->company('Oltin Mebel');

        $this->assertNull($this->importRow([
            'company' => 'Oltin Mebel',
            'author_company' => 'Компания, которой нет',
            'rating' => 5,
            'body' => 'Текст отзыва достаточной длины.',
        ]));

        $this->assertSame(0, Review::query()->count());
    }

    /** Компания о самой себе — не отзыв, даже из файла. */
    #[Test]
    public function отзыв_о_самом_себе_пропускается(): void
    {
        $this->company('Oltin Mebel');

        $this->assertNull($this->importRow([
            'company' => 'Oltin Mebel',
            'author_company' => 'Oltin Mebel',
            'rating' => 5,
            'body' => 'Мы прекрасны, рекомендуем себя.',
        ]));
    }

    /** Повторная загрузка того же файла не плодит дублей. */
    #[Test]
    public function повтор_обновляет_существующий_отзыв(): void
    {
        $this->company('Oltin Mebel');
        $this->company('Stroy Invest');

        $row = [
            'company' => 'Oltin Mebel',
            'author_company' => 'Stroy Invest',
            'rating' => 3,
            'body' => 'Первая редакция текста отзыва.',
        ];

        $first = $this->importRow($row);
        $second = $this->importRow([...$row, 'rating' => 5, 'body' => 'Исправленная редакция текста отзыва.']);

        $this->assertSame($first->id, $second->id, 'повтор обязан обновлять, а не плодить');
        $this->assertSame(1, Review::query()->count());
        $this->assertSame(5, $second->fresh()->rating);
    }

    // ── Разбор оценки ───────────────────────────────────────────────

    /** Оценку пишут по-разному: «5», «5 звёзд», «4/5». */
    #[Test]
    public function оценка_вынимается_из_разных_написаний(): void
    {
        $method = new \ReflectionMethod(ReviewImporter::class, 'rating');

        foreach (['5' => 5, '5 звёзд' => 5, '4/5' => 4, '  3  ' => 3] as $written => $expected) {
            $this->assertSame($expected, $method->invoke(null, (string) $written), "«{$written}» это {$expected}");
        }
    }

    /**
     * Строка без числа не превращается в единицу молча.
     *
     * Молчаливая единица — это чужой рейтинг, испорченный опечаткой
     * в файле. Пусть лучше строка не загрузится и будет названа
     * в итогах.
     */
    #[Test]
    public function невнятная_оценка_не_становится_единицей(): void
    {
        $method = new \ReflectionMethod(ReviewImporter::class, 'rating');

        foreach (['', 'отлично', '—', '0', '9'] as $written) {
            $this->assertNull($method->invoke(null, $written), "«{$written}» не оценка");
        }
    }
}
