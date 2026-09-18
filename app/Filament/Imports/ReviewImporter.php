<?php

declare(strict_types=1);

namespace App\Filament\Imports;

use App\Models\Company;
use App\Models\Review;
use App\Support\ImportCell;
use Filament\Actions\Imports\ImportColumn;
use Filament\Actions\Imports\Importer;
use Filament\Actions\Imports\Models\Import;
use Illuminate\Support\Facades\Auth;

/**
 * Загрузка отзывов пачкой.
 *
 * Нужна для переноса: отзывы со старой площадки, собранные на выставке,
 * присланные почтой. Компании задаются названием, а не номером — номер
 * менеджеру неоткуда взять.
 *
 * Каждая строка помечается происхождением: в админке видно, какая часть
 * рейтинга пришла от покупателей, а какая загружена файлом. Без этого
 * рейтинг перестаёт что-либо значить, а первым это почувствует покупатель,
 * выбравший поставщика по нему.
 *
 * Повторная загрузка того же файла не плодит дублей: в базе один отзыв
 * на пару «автор — компания — объявление», и совпавшая пара обновляется.
 */
class ReviewImporter extends Importer
{
    protected static ?string $model = Review::class;

    public static function getColumns(): array
    {
        return [
            ImportColumn::make('company')
                ->label('О какой компании')
                ->exampleHeader('О какой компании')
                ->example('Oltin Mebel')
                ->requiredMapping()
                ->rules(['required', 'string', 'max:190']),

            ImportColumn::make('author_company')
                ->label('От какой компании')
                ->exampleHeader('От какой компании')
                ->example('Stroy Invest')
                ->requiredMapping()
                ->rules(['required', 'string', 'max:190']),

            ImportColumn::make('rating')
                ->label('Оценка')
                ->exampleHeader('Оценка')
                ->example('5')
                ->requiredMapping()
                ->castStateUsing(fn (?string $state): ?int => self::rating($state))
                ->rules(['required', 'integer', 'min:1', 'max:5']),

            ImportColumn::make('body')
                ->label('Текст отзыва')
                ->exampleHeader('Текст отзыва')
                ->example('Отгрузили вовремя, качество соответствует описанию.')
                ->requiredMapping()
                ->castStateUsing(fn (?string $state): ?string => ImportCell::text($state, 5000))
                ->rules(['required', 'string', 'min:10', 'max:5000']),

            ImportColumn::make('reply')
                ->label('Ответ компании')
                ->exampleHeader('Ответ компании')
                ->example('Спасибо за отзыв, ждём снова.')
                ->castStateUsing(fn (?string $state): ?string => ImportCell::text($state, 5000))
                ->rules(['nullable', 'string', 'max:5000']),
        ];
    }

    /**
     * Оценка: цифра от одного до пяти.
     *
     * Встречается «5 звёзд», «4/5», «отлично» — берём первое число
     * в диапазоне, остальное отбрасываем. Строка без числа отменяется
     * правилом выше, а не молча превращается в единицу.
     */
    private static function rating(?string $state): ?int
    {
        if ($state === null || trim($state) === '') {
            return null;
        }

        preg_match('/[1-5]/', $state, $found);

        return isset($found[0]) ? (int) $found[0] : null;
    }

    /**
     * Строка файла превращается в отзыв.
     *
     * Компания ищется по названию, без учёта регистра и лишних
     * пробелов. Не нашлась — строка пропускается: завести отзыв
     * о несуществующей компании хуже, чем не завести его вовсе.
     */
    public function resolveRecord(): ?Review
    {
        $about = $this->company($this->data['company'] ?? null);
        $author = $this->company($this->data['author_company'] ?? null);

        if ($about === null || $author === null || $about->id === $author->id) {
            return null;
        }

        // Пара «автор — компания — объявление» уникальна в базе,
        // поэтому совпавшая строка обновляет существующий отзыв
        $review = Review::firstOrNew([
            'company_id' => $about->id,
            'author_company_id' => $author->id,
            'listing_id' => null,
        ]);

        $review->origin = Review::ORIGIN_IMPORT;
        $review->created_by = Auth::id();
        $review->status ??= Review::STATUS_PUBLISHED;

        return $review;
    }

    private function company(?string $name): ?Company
    {
        $name = trim((string) $name);

        if ($name === '') {
            return null;
        }

        return Company::query()
            ->whereRaw('LOWER(name) = ?', [mb_strtolower($name)])
            ->first();
    }

    public static function getCompletedNotificationBody(Import $import): string
    {
        $done = $import->successful_rows;
        $failed = $import->getFailedRowsCount();

        $body = "Загружено отзывов: {$done}.";

        if ($failed > 0) {
            // Чаще всего — незнакомое название компании: в файле оно
            // написано иначе, чем в справочнике
            $body .= " Пропущено строк: {$failed}. Обычно это ненайденная компания — проверьте написание названий.";
        }

        return $body;
    }
}
