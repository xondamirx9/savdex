<?php

declare(strict_types=1);

namespace App\Services;

use App\Models\Listing;
use App\Models\User;
use App\Support\CatalogLookup;
use App\Support\ImageStore;
use App\Support\ImportLanguage;
use App\Support\WorkbookImages;
use Illuminate\Support\Facades\File;
use Illuminate\Support\Str;
use OpenSpout\Common\Entity\Row;
use OpenSpout\Reader\XLSX\Options;
use OpenSpout\Reader\XLSX\Reader;
use RuntimeException;
use Throwable;

/**
 * Загрузка товаров из книги Excel вместе с фотографиями.
 *
 * Обычный импорт Filament принимает только CSV, а в CSV картинку не
 * положишь: заказчик собирает каталог в Excel, вставляя фотографии
 * прямо в ячейки. Поэтому книга читается целиком — значения берёт
 * openspout, фотографии достаёт WorkbookImages, — и то и другое
 * сходится по номеру строки.
 *
 * Что делает загрузка со строкой:
 *
 *  — «Номер» заполнен → правится это объявление;
 *  — иначе ищется по заголовку и компании;
 *  — не нашлось → заводится новое (без компании нельзя: объявление
 *    без продавца не показать).
 *
 * Фотографии добавляются только объявлениям, у которых их нет:
 * повторная загрузка того же файла не должна плодить одинаковые
 * снимки. Заменить имеющиеся можно галочкой в окне загрузки.
 */
final class ListingWorkbookImport
{
    public function __construct(private readonly ImageStore $images) {}

    /**
     * @return array{rows: int, created: int, updated: int, photos: int, errors: list<string>}
     */
    public function run(string $workbook, User $author, bool $replacePhotos = false): array
    {
        $directory = storage_path('app/listing-workbook/'.Str::random(16));
        $photos = WorkbookImages::extract($workbook, $directory);

        $result = ['rows' => 0, 'created' => 0, 'updated' => 0, 'photos' => 0, 'errors' => []];

        try {
            $options = new Options;

            // Пустые строки нужны: без них номера строк сползают, и
            // фотография из седьмой строки достаётся пятому товару
            $options->SHOULD_PRESERVE_EMPTY_ROWS = true;

            $reader = new Reader($options);
            $reader->open($workbook);

            try {
                foreach ($reader->getSheetIterator() as $sheet) {
                    $this->readSheet($sheet->getRowIterator(), $photos, $author, $replacePhotos, $result);

                    // Товары лежат на первом листе; остальные — справочники
                    // и заметки, разбирать их как каталог незачем
                    break;
                }
            } finally {
                $reader->close();
            }
        } finally {
            File::deleteDirectory($directory);
        }

        return $result;
    }

    /**
     * @param  iterable<Row>  $rows
     * @param  array<int, list<string>>  $photos
     * @param  array{rows: int, created: int, updated: int, photos: int, errors: list<string>}  $result
     */
    private function readSheet(iterable $rows, array $photos, User $author, bool $replace, array &$result): void
    {
        $columns = null;
        $number = 0;

        foreach ($rows as $row) {
            $number++;
            $values = $row->toArray();

            if ($columns === null) {
                $columns = $this->columns($values);

                // Пока ни один заголовок не узнан, это шапка отчёта
                // или пустые строки перед таблицей
                if ($columns === []) {
                    $columns = null;
                }

                continue;
            }

            $fields = $this->fields($columns, $values);

            if ($fields === [] && ! isset($photos[$number])) {
                continue;
            }

            $result['rows']++;

            try {
                $this->saveRow($fields, $photos[$number] ?? [], $author, $replace, $result);
            } catch (RuntimeException $e) {
                $result['errors'][] = 'Строка '.$number.': '.$e->getMessage();
            } catch (Throwable $e) {
                report($e);
                $result['errors'][] = 'Строка '.$number.': строку не удалось загрузить';
            }
        }
    }

    /**
     * @param  array<string, string>  $fields
     * @param  list<string>  $files
     * @param  array{rows: int, created: int, updated: int, photos: int, errors: list<string>}  $result
     */
    private function saveRow(array $fields, array $files, User $author, bool $replace, array &$result): void
    {
        $listing = $this->resolve($fields);
        $exists = $listing->exists;

        $this->fill($listing, $fields, $author);
        $listing->save();

        if (blank($listing->slug)) {
            $listing->slug = Listing::makeSlug($listing->title, $listing->id);
            $listing->saveQuietly();
        }

        $result[$exists ? 'updated' : 'created']++;
        $result['photos'] += $this->attach($listing, $files, $replace);
    }

    /**
     * Объявление, к которому относится строка.
     *
     * @param  array<string, string>  $fields
     */
    private function resolve(array $fields): Listing
    {
        $id = (int) preg_replace('/\D/', '', $fields['id'] ?? '');

        if ($id > 0) {
            $listing = Listing::query()->find($id);

            if ($listing === null) {
                throw new RuntimeException('объявление № '.$id.' не найдено');
            }

            return $listing;
        }

        $title = trim($fields['title'] ?? '');

        if ($title === '') {
            throw new RuntimeException('не заполнен заголовок');
        }

        $companyId = $this->companyId($fields);

        $found = Listing::query()
            ->where('title', $title)
            ->when($companyId !== null, fn ($q) => $q->where('company_id', $companyId))
            ->first();

        if ($found !== null) {
            return $found;
        }

        if ($companyId === null) {
            throw new RuntimeException('не указана компания, а без неё новое объявление не создать');
        }

        return new Listing(['company_id' => $companyId]);
    }

    /** @param array<string, string> $fields */
    private function companyId(array $fields): ?int
    {
        $company = trim($fields['company'] ?? '');

        if ($company === '') {
            return null;
        }

        $id = CatalogLookup::companyId($company);

        if ($id === null) {
            throw new RuntimeException('компания «'.$company.'» не найдена в справочнике');
        }

        return $id;
    }

    /** @param array<string, string> $fields */
    private function fill(Listing $listing, array $fields, User $author): void
    {
        if (! $listing->exists) {
            $listing->user_id = $author->id;
            $listing->type = Listing::TYPE_SUPPLY;
            $listing->status = Listing::STATUS_ACTIVE;
        }

        if (($company = $this->companyId($fields)) !== null) {
            $listing->company_id = $company;
        }

        foreach (['title', 'description', 'unit'] as $plain) {
            if (trim($fields[$plain] ?? '') !== '') {
                $listing->{$plain} = trim($fields[$plain]);
            }
        }

        if (trim($fields['category_id'] ?? '') !== '') {
            $category = CatalogLookup::categoryId($fields['category_id']);

            if ($category === null) {
                throw new RuntimeException('категория «'.trim($fields['category_id']).'» не найдена в каталоге');
            }

            $listing->category_id = $category;
        }

        if (trim($fields['city_id'] ?? '') !== '') {
            $city = CatalogLookup::cityId($fields['city_id']);

            if ($city === null) {
                throw new RuntimeException('город «'.trim($fields['city_id']).'» не найден в справочнике');
            }

            $listing->city_id = $city;
        }

        if (trim($fields['type'] ?? '') !== '') {
            $listing->type = $this->type($fields['type']);
        }

        if (trim($fields['price'] ?? '') !== '') {
            $listing->price = ImportLanguage::amount($fields['price']);
            $listing->price_negotiable = $listing->price === null;
        }

        if (trim($fields['currency'] ?? '') !== '') {
            $listing->currency = ImportLanguage::currency($fields['currency']);
        }

        if (trim($fields['min_order'] ?? '') !== '') {
            $listing->min_order = (int) (ImportLanguage::amount($fields['min_order']) ?? 0) ?: null;
        }

        if (trim($fields['status'] ?? '') !== '') {
            $listing->status = ImportLanguage::isYes($fields['status'])
                ? Listing::STATUS_ACTIVE
                : Listing::STATUS_MODERATION;
        }

        $listing->currency = $listing->currency ?: 'UZS';

        // Опубликованному объявлению нужен срок: без него оно не
        // попадает ни в один список витрины
        if ($listing->status === Listing::STATUS_ACTIVE) {
            $listing->published_at ??= now();
            $listing->expires_at ??= now()->addDays(Listing::LIFETIME_DAYS);
        }
    }

    /**
     * Фотографии строки — объявлению.
     *
     * @param  list<string>  $files
     */
    private function attach(Listing $listing, array $files, bool $replace): int
    {
        if ($files === []) {
            return 0;
        }

        $already = $listing->images()->count();

        if ($already > 0) {
            if (! $replace) {
                return 0;
            }

            foreach ($listing->images()->get() as $image) {
                $this->images->delete($image->path, $image->thumb_path);
                $image->delete();
            }

            $already = 0;
        }

        $saved = 0;

        foreach (array_slice($files, 0, Listing::MAX_IMAGES) as $file) {
            try {
                $paths = $this->images->storeWithThumb($file, "listings/{$listing->id}");
            } catch (RuntimeException) {
                // Одна нечитаемая картинка не должна ронять строку
                continue;
            }

            $listing->images()->create([...$paths, 'sort' => $already + $saved]);
            $saved++;
        }

        return $saved;
    }

    private function type(string $value): string
    {
        $needle = ImportLanguage::normalize($value);

        // Перечислены только слова запроса: всё остальное — предложение,
        // и незнакомое слово попадает в предложения, а не теряет строку
        $demand = ['запрос', 'спрос', 'закупка', 'покупка', 'куплю', 'потребность',
            'demand', 'request', 'rfq', 'buy', 'buying', 'purchase',
            'talab', 'sotib olish', 'xarid', 'talep', 'alım', 'satın alma',
            '采购', '求购', '需求'];

        return in_array($needle, $demand, true) ? Listing::TYPE_DEMAND : Listing::TYPE_SUPPLY;
    }

    /**
     * Шапка таблицы: номер колонки → поле объявления.
     *
     * @param  list<mixed>  $values
     * @return array<int, string>
     */
    private function columns(array $values): array
    {
        $columns = [];
        $taken = [];

        foreach ($values as $index => $value) {
            foreach (ImportLanguage::LISTING_HEADERS as $field => $aliases) {
                if (in_array($field, $taken, true) || ! ImportLanguage::matches($this->text($value), $aliases)) {
                    continue;
                }

                $columns[$index] = $field;
                $taken[] = $field;

                break;
            }
        }

        return $columns;
    }

    /**
     * @param  array<int, string>  $columns
     * @param  list<mixed>  $values
     * @return array<string, string>
     */
    private function fields(array $columns, array $values): array
    {
        $fields = [];

        foreach ($columns as $index => $field) {
            $text = $this->text($values[$index] ?? null);

            if ($text !== '') {
                $fields[$field] = $text;
            }
        }

        return $fields;
    }

    private function text(mixed $value): string
    {
        if ($value instanceof \DateTimeInterface) {
            return $value->format('d.m.Y');
        }

        if (is_bool($value)) {
            return $value ? 'да' : 'нет';
        }

        if (is_float($value) && $value === floor($value)) {
            // Excel отдаёт целые числа дробными: «Номер 12» иначе
            // превращается в «12.0» и не находит объявление
            return (string) (int) $value;
        }

        return trim((string) ($value ?? ''));
    }
}
