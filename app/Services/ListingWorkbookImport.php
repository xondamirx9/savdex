<?php

declare(strict_types=1);

namespace App\Services;

use App\Models\Listing;
use App\Models\User;
use App\Support\CatalogLookup;
use App\Support\Currencies;
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
 * Книга — до пяти листов, по одному на язык. Лист узнаётся по имени
 * вкладки (ImportLanguage::SHEET_LOCALES); без узнаваемых имён
 * главным считается первый лист, как в книге на одном языке.
 *
 *  — русский лист главный: с него берутся цена, валюта, категория,
 *    компания, город и фотографии — всё, что у товара одно на все
 *    языки;
 *  — остальные листы отдают только тексты: заголовок, описание,
 *    условия поставки и оплаты — строка к строке с русским листом.
 *    Пятая строка английского листа — тот же товар, что пятая
 *    строка русского. Другой связи нет, поэтому число строк на
 *    листах обязано совпадать: иначе переводы съедут на соседний
 *    товар, и никто этого не заметит.
 *
 * Что делает загрузка со строкой русского листа:
 *
 *  — «Номер» заполнен → правится это объявление;
 *  — иначе ищется по заголовку и компании;
 *  — не нашлось → заводится новое (без компании нельзя: объявление
 *    без продавца не показать).
 *
 * Новое объявление ждёт проверки: администратор публикует его
 * из списка. Уже опубликованное повторная загрузка не снимает —
 * только обновляет тексты и цену.
 *
 * Фотографии добавляются только объявлениям, у которых их нет:
 * повторная загрузка того же файла не должна плодить одинаковые
 * снимки. Заменить имеющиеся можно галочкой в окне загрузки.
 */
final class ListingWorkbookImport
{
    /**
     * Ячейки, которые пришлось пропустить в текущей строке.
     *
     * Непонятная ячейка не отменяет строку: незнакомая категория,
     * город не из справочника, валюта, которой у площадки нет, —
     * пропускаются, а объявление загружается. Файл на триста товаров
     * не должен разворачиваться из-за опечатки в одной клетке.
     * Пропущенное попадает в отчёт: молча потерянная цена хуже
     * загруженного объявления без неё.
     *
     * @var list<string>
     */
    private array $skipped = [];

    /** Компания из строки, которую не нашли в справочнике. */
    private ?string $unknownCompany = null;

    public function __construct(private readonly ImageStore $images) {}

    /**
     * @return array{rows: int, created: int, updated: int, photos: int, errors: list<string>, notes: list<string>}
     */
    public function run(string $workbook, User $author, bool $replacePhotos = false): array
    {
        $result = ['rows' => 0, 'created' => 0, 'updated' => 0, 'photos' => 0, 'errors' => [], 'notes' => []];

        $sheets = $this->sheets($workbook, $result);
        $roles = $this->roles($sheets, $result);

        if ($roles === null) {
            return $result;
        }

        [$master, $translations] = $roles;

        if (! $this->aligned($master, $translations, $result)) {
            return $result;
        }

        $directory = storage_path('app/listing-workbook/'.Str::random(16));
        $photos = WorkbookImages::extract($workbook, $directory, $master['name']);

        // Строка называется с листом, только когда листов несколько:
        // в книге на одном языке «Лист «Лист1», строка 5» — лишний шум
        $named = $translations !== [];

        try {
            foreach ($master['rows'] as $offset => $row) {
                $fields = $row['fields'];
                $number = $row['number'];

                if ($fields === [] && ! isset($photos[$number])) {
                    continue;
                }

                $result['rows']++;

                $texts = [];

                foreach ($translations as $locale => $sheet) {
                    if (isset($sheet['rows'][$offset])) {
                        $texts[$locale] = $sheet['rows'][$offset]['fields'];
                    }
                }

                try {
                    $this->saveRow($fields, $texts, $photos[$number] ?? [], $author, $replacePhotos, $result);

                    // Что в строке пропущено — в отчёт: строка загружена,
                    // но человек должен знать, чего в ней не хватает
                    foreach ($this->skipped as $skip) {
                        $result['notes'][] = $this->where($master, $number, $named).': '.$skip;
                    }
                } catch (RuntimeException $e) {
                    $result['errors'][] = $this->where($master, $number, $named).': '.$e->getMessage();
                } catch (Throwable $e) {
                    report($e);
                    $result['errors'][] = $this->where($master, $number, $named).': строку не удалось загрузить';
                }
            }
        } finally {
            File::deleteDirectory($directory);
        }

        return $result;
    }

    /**
     * Листы книги с разобранными строками.
     *
     * Читаются те, что могут понадобиться: первый видимый (главный,
     * если русского по имени нет) и все с узнаваемым именем языка.
     * Скрытые вкладки не читаются вовсе: человек их в Excel не видит,
     * и лист «English» с примером из образца, спрятанный вместо
     * удаления, стал бы переводом его товаров. Прочие — справочники
     * и заметки — пропускаются с заметкой в отчёте: вкладка «Eng.»
     * с переводами, которую загрузка не узнала, иначе теряется молча
     * за зелёным «Загрузка завершена».
     *
     * @param  array{notes: list<string>}  $result
     * @return list<array{name: string, locale: string|null, header: int|null, last: int, rows: array<int, array{number: int, fields: array<string, string>}>}>
     */
    private function sheets(string $workbook, array &$result): array
    {
        $options = new Options;

        // Пустые строки нужны: без них номера строк сползают, и
        // фотография из седьмой строки достаётся пятому товару
        $options->SHOULD_PRESERVE_EMPTY_ROWS = true;

        $reader = new Reader($options);
        $reader->open($workbook);

        $sheets = [];

        try {
            foreach ($reader->getSheetIterator() as $sheet) {
                $name = $sheet->getName();

                if (! $sheet->isVisible()) {
                    $result['notes'][] = 'Скрытый лист «'.$name.'» пропущен.';

                    continue;
                }

                $locale = ImportLanguage::sheetLocale($name);

                if ($locale === null && $sheets !== []) {
                    $result['notes'][] = 'Лист «'.$name.'» пропущен: имя вкладки не узнано как язык. '
                        .'Языковые вкладки называются «Русский», «English», «O‘zbekcha», «中文», «Türkçe» — как в образце.';

                    continue;
                }

                $sheets[] = ['name' => $name, 'locale' => $locale, ...$this->readSheet($sheet->getRowIterator())];
            }
        } finally {
            $reader->close();
        }

        return $sheets;
    }

    /**
     * Строки одного листа: шапка и всё, что под ней.
     *
     * Номер строки — как в Excel, с единицы и с учётом всего, что
     * стоит над шапкой; по нему сходятся фотографии. Смещение от
     * шапки — ключ массива: по нему сходятся листы между собой.
     *
     * @param  iterable<Row>  $rows
     * @return array{header: int|null, last: int, rows: array<int, array{number: int, fields: array<string, string>}>}
     */
    private function readSheet(iterable $rows): array
    {
        $columns = null;
        $header = null;
        $number = 0;
        $last = 0;
        $parsed = [];

        foreach ($rows as $row) {
            $number++;
            $values = $row->toArray();

            if ($columns === null) {
                $columns = $this->columns($values);

                // Пока ни один заголовок не узнан, это шапка отчёта
                // или пустые строки перед таблицей
                if ($columns === []) {
                    $columns = null;
                } else {
                    $header = $number;
                }

                continue;
            }

            $fields = $this->fields($columns, $values);
            $offset = $number - $header;
            $parsed[$offset] = ['number' => $number, 'fields' => $fields];

            if ($fields !== []) {
                $last = $offset;
            }
        }

        return ['header' => $header, 'last' => $last, 'rows' => $parsed];
    }

    /**
     * Какой лист главный и какие — переводы.
     *
     * @param  list<array{name: string, locale: string|null, header: int|null, last: int, rows: array<int, array{number: int, fields: array<string, string>}>}>  $sheets
     * @param  array{errors: list<string>, notes: list<string>}  $result
     * @return array{0: array{name: string, locale: string|null, header: int|null, last: int, rows: array<int, array{number: int, fields: array<string, string>}>}, 1: array<string, array{name: string, locale: string|null, header: int|null, last: int, rows: array<int, array{number: int, fields: array<string, string>}>}>}|null
     */
    private function roles(array $sheets, array &$result): ?array
    {
        if ($sheets === []) {
            return null;
        }

        $byLocale = [];

        foreach ($sheets as $sheet) {
            if ($sheet['locale'] === null) {
                continue;
            }

            if (isset($byLocale[$sheet['locale']])) {
                $result['errors'][] = 'Два листа на одном языке: «'.$byLocale[$sheet['locale']]['name'].'» и «'
                    .$sheet['name'].'». Оставьте один — книга не загружена.';

                return null;
            }

            $byLocale[$sheet['locale']] = $sheet;
        }

        $master = $byLocale['ru'] ?? null;

        // Русского по имени нет: главный — первый лист, если он
        // не подписан другим языком. Книга из одного листа «Лист1»
        // остаётся книгой на русском, как и раньше
        if ($master === null) {
            if ($sheets[0]['locale'] !== null) {
                $result['errors'][] = 'В книге нет русского листа. Назовите вкладку с ценами и фотографиями «Русский» — '
                    .'она главная, остальные листы дают только переводы. Книга не загружена.';

                return null;
            }

            $master = $sheets[0];
        }

        if ($master['header'] === null) {
            $result['errors'][] = 'Лист «'.$master['name'].'»: не найдена строка с названиями столбцов. '
                .'Скачайте образец книги — в нём столбцы названы так, как их ждёт загрузка.';

            return null;
        }

        unset($byLocale['ru']);

        return [$master, $byLocale];
    }

    /**
     * Строки листов совпадают — иначе переводы съедут.
     *
     * Проверяется и число строк, и что напротив каждой заполненной
     * строки перевода стоит заполненная русская: текст переводчика
     * напротив пустой русской строки — верный признак, что строки
     * съехали (в русском листе строку стёрли, а внизу дописали).
     * Ловить это только по числу строк нельзя — число совпадает.
     *
     * Лист без шапки — ошибка: он подписан языком, но таблицы в нём
     * не нашлось. Лист с одной шапкой — просто нет переводов на этот
     * язык, это отмечается, но не мешает загрузке.
     *
     * @param  array{name: string, last: int, rows: array<int, array{number: int, fields: array<string, string>}>}  $master
     * @param  array<string, array{name: string, header: int|null, last: int, rows: array<int, array{number: int, fields: array<string, string>}>}>  $translations
     * @param  array{errors: list<string>, notes: list<string>}  $result
     */
    private function aligned(array $master, array &$translations, array &$result): bool
    {
        foreach ($translations as $locale => $sheet) {
            if ($sheet['header'] === null) {
                $result['errors'][] = 'Лист «'.$sheet['name'].'»: не найдена строка с названиями столбцов '
                    .'(Заголовок, Описание, Условия поставки, Условия оплаты). Книга не загружена.';

                return false;
            }

            if ($sheet['last'] === 0) {
                $result['notes'][] = 'Лист «'.$sheet['name'].'» пуст — переводов на этот язык нет.';
                unset($translations[$locale]);

                continue;
            }

            if ($sheet['last'] !== $master['last']) {
                $result['errors'][] = 'Лист «'.$sheet['name'].'»: строк с данными '.$sheet['last']
                    .', на русском листе '.$master['last'].'. Переводы связаны по порядку строк, при разном '
                    .'числе строк они разъедутся по чужим товарам. Если перевода нет, оставьте строку '
                    .'пустой, но не удаляйте её. Книга не загружена.';

                return false;
            }

            foreach ($sheet['rows'] as $offset => $row) {
                if ($row['fields'] !== [] && ($master['rows'][$offset]['fields'] ?? []) === []) {
                    $result['errors'][] = 'Лист «'.$sheet['name'].'», строка '.$row['number']
                        .': заполнена, а на русском листе строка '.($master['rows'][$offset]['number'] ?? $row['number'])
                        .' пуста — строки разъехались. Книга не загружена.';

                    return false;
                }
            }
        }

        return true;
    }

    /** @param array{name: string} $sheet */
    private function where(array $sheet, int $number, bool $named): string
    {
        return $named ? 'Лист «'.$sheet['name'].'», строка '.$number : 'Строка '.$number;
    }

    /**
     * @param  array<string, string>  $fields
     * @param  array<string, array<string, string>>  $texts  язык → переводимые поля
     * @param  list<string>  $files
     * @param  array{rows: int, created: int, updated: int, photos: int, errors: list<string>, notes: list<string>}  $result
     */
    private function saveRow(array $fields, array $texts, array $files, User $author, bool $replace, array &$result): void
    {
        $listing = $this->resolve($fields);
        $exists = $listing->exists;

        $this->fill($listing, $fields, $author);
        $this->translate($listing, $texts);
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
            ->limit(2)
            ->get();

        // Без компании один заголовок может стоять у разных продавцов:
        // править первый попавшийся — значит менять цену чужого товара
        if ($found->count() > 1) {
            throw new RuntimeException('заголовок «'.$title.'» есть у нескольких объявлений — укажите «Номер» или «Компанию»');
        }

        if ($found->isNotEmpty()) {
            return $found->first();
        }

        if ($companyId === null) {
            throw new RuntimeException($this->unknownCompany !== null
                ? 'компания «'.$this->unknownCompany.'» не найдена в справочнике, а без компании новое объявление не создать'
                : 'не указана компания, а без неё новое объявление не создать');
        }

        return new Listing(['company_id' => $companyId]);
    }

    /** @param array<string, string> $fields */
    private function companyId(array $fields): ?int
    {
        $company = trim($fields['company'] ?? '');
        $this->unknownCompany = null;

        if ($company === '') {
            return null;
        }

        $id = CatalogLookup::companyId($company);

        if ($id === null) {
            // У нового объявления без компании нет продавца — там это
            // остановит строку (resolve). У существующего продавец уже
            // есть, и менять его по неузнанному названию нельзя
            $this->unknownCompany = $company;
            $this->skip('компания «'.$company.'» не найдена в справочнике — продавец остался прежним');

            return null;
        }

        return $id;
    }

    /** Ячейка, которую не удалось использовать. */
    private function skip(string $reason): void
    {
        $this->skipped[] = $reason;
    }

    /** @param array<string, string> $fields */
    private function fill(Listing $listing, array $fields, User $author): void
    {
        if (! $listing->exists) {
            $listing->user_id = $author->id;
            $listing->type = Listing::TYPE_SUPPLY;
            // Ждёт проверки: публикует администратор из списка,
            // посмотрев, что получилось
            $listing->status = Listing::STATUS_MODERATION;
        }

        // Загруженное помечается всегда, и при обновлении тоже:
        // объявление, которое ведут книгой, живёт по правилам книги
        $listing->source = Listing::SOURCE_IMPORT;

        if (($company = $this->companyId($fields)) !== null) {
            $listing->company_id = $company;
        }

        foreach (['title', 'description', 'unit', 'delivery_terms', 'payment_terms'] as $plain) {
            if (trim($fields[$plain] ?? '') !== '') {
                $listing->{$plain} = $this->fits($plain, trim($fields[$plain]));
            }
        }

        if (trim($fields['category_id'] ?? '') !== '') {
            $category = CatalogLookup::categoryId($fields['category_id']);

            if ($category === null) {
                $this->skip('категория «'.trim($fields['category_id']).'» не найдена в каталоге — ячейка пропущена');
            } else {
                $listing->category_id = $category;
            }
        }

        if (trim($fields['city_id'] ?? '') !== '') {
            $city = CatalogLookup::cityId($fields['city_id']);

            if ($city === null) {
                $this->skip('город «'.trim($fields['city_id']).'» не найден в справочнике — ячейка пропущена');
            } else {
                $listing->city_id = $city;
            }
        }

        if (trim($fields['type'] ?? '') !== '') {
            $listing->type = $this->type($fields['type']);
        }

        if (trim($fields['price'] ?? '') !== '') {
            $listing->price = ImportLanguage::amount($fields['price']);
            $listing->price_negotiable = $listing->price === null;
        }

        if (trim($fields['currency'] ?? '') !== '') {
            $currency = ImportLanguage::currency($fields['currency']);

            if (! Currencies::supports($currency)) {
                $this->skip('валюта «'.trim($fields['currency']).'» не поддерживается (можно: '
                    .implode(', ', Currencies::codes()).') — оставлена прежняя');
            } else {
                $listing->currency = $currency;
            }
        }

        if (trim($fields['min_order'] ?? '') !== '') {
            $listing->min_order = (int) (ImportLanguage::amount($fields['min_order']) ?? 0) ?: null;
        }

        $listing->currency = $listing->currency ?: 'UZS';

        // Опубликованному объявлению нужен срок: без него оно не
        // попадает ни в один список витрины. Новое сюда не попадает —
        // срок ему поставит публикация из админки
        if ($listing->status === Listing::STATUS_ACTIVE) {
            $listing->published_at ??= now();
            $listing->expires_at ??= now()->addDays(Listing::LIFETIME_DAYS);
        }
    }

    /**
     * Тексты с языковых листов — в переводные колонки.
     *
     * Пустая ячейка не стирает перевод, как и в остальных полях:
     * повторная загрузка книги, где переводчик ещё не дошёл до
     * строки, не должна обнулять то, что уже переведено.
     *
     * @param  array<string, array<string, string>>  $texts
     */
    private function translate(Listing $listing, array $texts): void
    {
        foreach ($texts as $locale => $values) {
            foreach (Listing::TRANSLATABLE as $field) {
                $value = trim($values[$field] ?? '');

                if ($value === '') {
                    continue;
                }

                $column = $field.'_i18n';
                $translations = $listing->{$column} ?? [];
                $translations[$locale] = $this->fits($field, $value, $locale);
                $listing->{$column} = $translations;
            }
        }
    }

    /**
     * Текст не длиннее, чем принимает форма.
     *
     * Иначе книга кладёт заголовок в 120 знаков, а админка потом
     * не даёт сохранить объявление, пока перевод не укоротят, —
     * и модератор не понимает, что не так с ценой, которую он правил.
     */
    private function fits(string $field, string $value, ?string $locale = null): string
    {
        $limit = Listing::MAX_LENGTH[$field] ?? null;

        if ($limit === null || mb_strlen($value) <= $limit) {
            return $value;
        }

        $labels = [
            'title' => 'заголовок',
            'description' => 'описание',
            'delivery_terms' => 'условия поставки',
            'payment_terms' => 'условия оплаты',
        ];

        /*
         * Длинный текст обрезается, а не отменяет строку: у заголовка
         * лишние символы — это хвост, а не смысл, и потерять из-за него
         * весь товар с фотографиями и ценой несоразмерно. Обрезка
         * попадает в отчёт — модератор допишет, если хвост был важен.
         */
        $this->skip(($labels[$field] ?? $field).($locale !== null ? ' на языке «'.$locale.'»' : '')
            .' длиннее '.$limit.' символов — обрезано');

        $cut = mb_substr($value, 0, $limit);
        $space = mb_strrpos($cut, ' ');

        return rtrim($space !== false && $space > $limit / 2 ? mb_substr($cut, 0, $space) : $cut, ' ,.;-');
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
