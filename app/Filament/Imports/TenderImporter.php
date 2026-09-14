<?php

declare(strict_types=1);

namespace App\Filament\Imports;

use App\Models\Category;
use App\Models\CategoryTranslation;
use App\Models\Country;
use App\Models\CountryTranslation;
use App\Models\Tender;
use Filament\Actions\Imports\Exceptions\RowImportFailedException;
use Filament\Actions\Imports\ImportColumn;
use Filament\Actions\Imports\Importer;
use Filament\Actions\Imports\Models\Import;
use Illuminate\Support\Carbon;
use Illuminate\Support\Facades\Auth;
use Throwable;

/**
 * Массовая загрузка тендеров из таблицы.
 *
 * Заголовки колонок русские — файл готовит менеджер в Excel и
 * сохраняет как CSV. Категория и страна задаются названием (или
 * кодом), а не id: id менеджеру неоткуда взять.
 *
 * Повторная загрузка того же файла не плодит дублей: тендер со
 * ссылкой на источник находится по ней и обновляется; без ссылки —
 * по заголовку и заказчику.
 *
 * Незнакомая категория или страна останавливает строку и попадает в
 * файл с ошибками: тендер без категории не виден ни в одном фильтре
 * витрины, и тихо потерять её хуже, чем не загрузить строку.
 */
class TenderImporter extends Importer
{
    protected static ?string $model = Tender::class;

    public static function getColumns(): array
    {
        return [
            ImportColumn::make('title')
                ->label('Заголовок')
                ->exampleHeader('Заголовок')
                ->example('Поставка цемента М400 для строительства школы')
                ->requiredMapping()
                ->rules(['required', 'string', 'max:190']),

            ImportColumn::make('description')
                ->label('Описание')
                ->exampleHeader('Описание')
                ->example('Требуется 500 тонн цемента М400, поставка партиями до 30 октября.')
                ->rules(['nullable', 'string', 'max:10000']),

            ImportColumn::make('customer')
                ->label('Заказчик')
                ->exampleHeader('Заказчик')
                ->example('ГУП «Тошкент шахар курилиш»')
                ->rules(['nullable', 'string', 'max:190']),

            ImportColumn::make('category_id')
                ->label('Категория')
                ->exampleHeader('Категория')
                ->example('Стройматериалы')
                ->castStateUsing(fn (?string $state): ?int => self::category($state))
                ->rules(['nullable', 'integer']),

            ImportColumn::make('country_id')
                ->label('Страна')
                ->exampleHeader('Страна')
                ->example('Узбекистан')
                ->castStateUsing(fn (?string $state): ?int => self::country($state))
                ->rules(['nullable', 'integer']),

            ImportColumn::make('location')
                ->label('Город')
                ->exampleHeader('Город')
                ->example('Ташкент')
                ->rules(['nullable', 'string', 'max:190']),

            ImportColumn::make('budget')
                ->label('Бюджет')
                ->exampleHeader('Бюджет')
                ->example('250000000')
                ->castStateUsing(fn (?string $state): ?float => self::money($state))
                ->rules(['nullable', 'numeric', 'min:0']),

            ImportColumn::make('currency')
                ->label('Валюта')
                ->exampleHeader('Валюта')
                ->example('UZS')
                ->castStateUsing(fn (?string $state): string => strtoupper(trim((string) $state)) ?: 'UZS')
                ->rules(['nullable', 'in:'.implode(',', Tender::CURRENCIES)]),

            ImportColumn::make('deadline_at')
                ->label('Приём заявок до')
                ->exampleHeader('Приём заявок до')
                ->example('30.10.2026')
                ->castStateUsing(fn (?string $state): ?string => self::date($state))
                ->rules(['nullable', 'date']),

            ImportColumn::make('source_url')
                ->label('Ссылка на источник')
                ->exampleHeader('Ссылка на источник')
                ->example('https://xarid.uzex.uz/...')
                ->rules(['nullable', 'url', 'max:255']),

            ImportColumn::make('contact_name')
                ->label('Контактное лицо')
                ->exampleHeader('Контактное лицо')
                ->rules(['nullable', 'string', 'max:190']),

            ImportColumn::make('contact_phone')
                ->label('Телефон')
                ->exampleHeader('Телефон')
                ->example('+998 71 200-00-00')
                ->rules(['nullable', 'string', 'max:40']),

            ImportColumn::make('contact_email')
                ->label('Почта')
                ->exampleHeader('Почта')
                ->rules(['nullable', 'email', 'max:190']),

            ImportColumn::make('status')
                ->label('Опубликовать')
                ->exampleHeader('Опубликовать')
                ->example('да')
                ->castStateUsing(fn (?string $state): string => self::yes($state)
                    ? Tender::STATUS_PUBLISHED
                    : Tender::STATUS_DRAFT)
                ->rules(['nullable', 'in:'.Tender::STATUS_DRAFT.','.Tender::STATUS_PUBLISHED]),
        ];
    }

    public function resolveRecord(): ?Tender
    {
        $url = trim((string) ($this->data['source_url'] ?? ''));

        if ($url !== '') {
            return Tender::firstOrNew(['source_url' => $url]);
        }

        $title = trim((string) ($this->data['title'] ?? ''));
        $customer = trim((string) ($this->data['customer'] ?? ''));

        if ($title === '') {
            return new Tender;
        }

        return Tender::firstOrNew(['title' => $title, 'customer' => $customer !== '' ? $customer : null]);
    }

    protected function beforeSave(): void
    {
        if (! $this->record->exists) {
            $this->record->author_id = Auth::id() ?? $this->import->user_id;
        }

        // Столбцов «Валюта» и «Опубликовать» в файле может не быть
        $this->record->currency = $this->record->currency ?: 'UZS';
        $this->record->status = $this->record->status ?: Tender::STATUS_DRAFT;

        if ($this->record->status === Tender::STATUS_PUBLISHED && $this->record->published_at === null) {
            $this->record->published_at = now();
        }
    }

    public static function getCompletedNotificationBody(Import $import): string
    {
        $body = 'Загрузка тендеров завершена. Обработано строк: '.number_format($import->successful_rows, 0, ',', ' ').'.';

        if (($failed = $import->getFailedRowsCount()) > 0) {
            $body .= ' Не удалось загрузить: '.number_format($failed, 0, ',', ' ')
                .'. Скачайте файл с ошибками — в нём причина по каждой строке.';
        }

        return $body;
    }

    // ── Разбор значений ──────────────────────────────────────

    /**
     * Категория по slug, названию на любом языке или пути
     * «Раздел → Подраздел» — так название копируют из админки.
     *
     * Сравнение в PHP, а не lower() в SQL: lower() SQLite не трогает
     * кириллицу, и «Стройматериалы» не нашлись бы по «стройматериалы».
     */
    private static function category(?string $state): ?int
    {
        $path = self::path($state);

        if ($path === []) {
            return null;
        }

        $id = self::findCategory($path);

        if ($id === null) {
            throw new RowImportFailedException(
                'Категория «'.trim((string) $state).'» не найдена в каталоге. '
                .'Впишите название так, как оно указано в разделе «Категории», или оставьте ячейку пустой.'
            );
        }

        return $id;
    }

    /**
     * Подкатегорию ищем по последней части пути, а раздел из пути
     * служит уточнением: подкатегорий «Другое» столько же, сколько
     * разделов, и без уточнения тендер попал бы в первый попавшийся.
     *
     * @param  list<string>  $path
     */
    private static function findCategory(array $path): ?int
    {
        $last = array_key_last($path);
        $name = $path[$last];
        $parentName = $last > 0 ? $path[$last - 1] : null;

        $categories = Category::query()->with('translations')->get();
        $matches = $categories->filter(fn (Category $c): bool => self::isNamed($c, $name));

        if ($matches->count() > 1 && $parentName !== null) {
            $narrowed = $matches->filter(function (Category $c) use ($categories, $parentName): bool {
                $parent = $categories->firstWhere('id', $c->parent_id);

                return $parent !== null && self::isNamed($parent, $parentName);
            });

            if ($narrowed->isNotEmpty()) {
                $matches = $narrowed;
            }
        }

        return $matches->first()?->id;
    }

    private static function isNamed(Category $category, string $needle): bool
    {
        if (self::normalize($category->slug) === $needle) {
            return true;
        }

        return $category->translations
            ->contains(fn (CategoryTranslation $t): bool => self::normalize($t->name) === $needle);
    }

    /** Страна по коду ISO («uz») или названию на любом языке. */
    private static function country(?string $state): ?int
    {
        $needle = self::normalize((string) $state);

        if ($needle === '') {
            return null;
        }

        $byCode = Country::query()->where('code', $needle)->value('id');

        if ($byCode !== null) {
            return (int) $byCode;
        }

        $match = CountryTranslation::query()
            ->get(['country_id', 'name'])
            ->first(fn (CountryTranslation $t): bool => self::normalize($t->name) === $needle);

        if ($match === null) {
            throw new RowImportFailedException(
                'Страна «'.trim((string) $state).'» не найдена в справочнике. '
                .'Напишите название целиком («Узбекистан») или код («UZ»), либо оставьте ячейку пустой.'
            );
        }

        return (int) $match->country_id;
    }

    /**
     * Значение ячейки — путь из нормализованных частей.
     *
     * «Стройматериалы → Цемент и бетон», «Стройматериалы / Цемент и
     * бетон» и просто «Цемент и бетон» приводятся к одному виду.
     *
     * @return list<string>
     */
    private static function path(?string $state): array
    {
        $parts = preg_split('#\s*(?:→|->|>|/|\\\\|\|)\s*#u', (string) $state) ?: [];
        $parts = array_map(self::normalize(...), $parts);

        return array_values(array_filter($parts, fn (string $part): bool => $part !== ''));
    }

    /**
     * Написание, набранное человеком, — к единому виду.
     *
     * Excel подставляет неразрывные пробелы, «ё» пишут через «е», а
     * узбекские названия — с четырьмя разными апострофами. Точное
     * сравнение на таких строках молча теряло категорию.
     */
    private static function normalize(string $value): string
    {
        $value = str_replace(
            ["\u{00A0}", "\u{202F}", "\u{2007}", "\u{200B}", 'ё', '«', '»', '"', '’', '‘', 'ʼ', 'ʻ', '`', '´'],
            [' ', ' ', ' ', '', 'е', '', '', '', "'", "'", "'", "'", "'", "'"],
            mb_strtolower($value),
        );

        return trim((string) preg_replace('/\s+/u', ' ', $value));
    }

    /** «250 000 000», «250000000,00» и «250 000 000 сум» — одно число. */
    private static function money(?string $state): ?float
    {
        $digits = preg_replace('/[^\d,.]/u', '', (string) $state) ?? '';
        $digits = str_replace(',', '.', $digits);

        if ($digits === '' || ! is_numeric($digits)) {
            return null;
        }

        return (float) $digits;
    }

    /** Дата в привычном «30.10.2026» или в ISO — в формат базы. */
    private static function date(?string $state): ?string
    {
        $raw = trim((string) $state);

        if ($raw === '') {
            return null;
        }

        foreach (['d.m.Y H:i', 'd.m.Y', 'Y-m-d H:i', 'Y-m-d', 'd/m/Y'] as $format) {
            try {
                $date = Carbon::createFromFormat($format, $raw);
            } catch (Throwable) {
                continue;
            }

            if ($date !== null) {
                // Без времени — конец дня: «до 30 октября» включает 30-е
                if (! str_contains($format, 'H')) {
                    $date->endOfDay();
                }

                return $date->toDateTimeString();
            }
        }

        return $raw;
    }

    private static function yes(?string $state): bool
    {
        return in_array(mb_strtolower(trim((string) $state)), ['да', 'yes', '1', 'true', 'ha', 'опубликовать'], true);
    }
}
