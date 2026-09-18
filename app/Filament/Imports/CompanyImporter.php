<?php

declare(strict_types=1);

namespace App\Filament\Imports;

use App\Filament\Imports\Concerns\MapsHeadersInAnyLanguage;
use App\Models\Company;
use App\Models\CompanyType;
use App\Models\CompanyTypeTranslation;
use App\Support\CatalogLookup;
use App\Support\CompanyNameStyle;
use App\Support\ImportCell;
use App\Support\ImportLanguage;
use Filament\Actions\Imports\ImportColumn;
use Filament\Actions\Imports\Importer;
use Filament\Actions\Imports\Models\Import;

/**
 * Импорт компаний из таблицы (§6.4 ТЗ).
 *
 * Сопоставление идёт по ИНН, а не по названию: «ООО Стройбаза»
 * и «ООО «Стройбаза»» — одна компания, а два разных ИНН означают
 * два разных юрлица даже при одинаковом названии.
 *
 * Заголовки колонок русские: файл готовит заказчик в Excel,
 * и требовать от него slug и primary_role бессмысленно. Но язык
 * файла любой — заголовки и тип компании узнаются на пяти языках
 * площадки, словари в App\Support\ImportLanguage.
 *
 * Сами ячейки тоже набраны руками: прочерк вместо пустоты, две почты
 * через косую черту, «около 6500 (по публичным данным)» в численности.
 * Такую ячейку приводит к виду колонки App\Support\ImportCell —
 * компания не должна теряться из-за второго телефона.
 */
class CompanyImporter extends Importer
{
    use MapsHeadersInAnyLanguage;

    protected static ?string $model = Company::class;

    public static function getColumns(): array
    {
        return [
            ImportColumn::make('tin')
                ->label('ИНН')
                ->exampleHeader('ИНН')
                ->guess(ImportLanguage::COMPANY_HEADERS['tin'])
                ->example('304561278')
                // Прочерк в ИНН — это «нет ИНН», а не общий для всех
                // иностранных компаний номер, по которому они слипнутся
                ->castStateUsing(fn (?string $state): ?string => ImportCell::first($state, 20))
                ->rules(['nullable', 'string', 'max:20']),

            ImportColumn::make('name')
                ->label('Название')
                ->exampleHeader('Название')
                ->guess(ImportLanguage::COMPANY_HEADERS['name'])
                ->example('ООО «Стройбаза»')
                ->requiredMapping()
                // Госреестр пишет капсом — на витрине это выглядит криком
                ->castStateUsing(fn (?string $state): string => CompanyNameStyle::humanize(
                    (string) ImportCell::text($state, 190),
                ))
                ->rules(['required', 'string', 'max:190']),

            ImportColumn::make('legal_name')
                ->label('Юридическое название')
                ->exampleHeader('Юридическое название')
                ->guess(ImportLanguage::COMPANY_HEADERS['legal_name'])
                ->castStateUsing(fn (?string $state): ?string => ImportCell::text($state, 255))
                ->rules(['nullable', 'string', 'max:255']),

            ImportColumn::make('type')
                ->label('Тип компании')
                ->exampleHeader('Тип компании')
                ->guess(ImportLanguage::COMPANY_HEADERS['type'])
                ->example('distributor')
                // «производство, экспорт, торговля» — берём первое:
                // тип у компании один, остальное расскажет описание
                ->castStateUsing(fn (?string $state): ?string => self::type(ImportCell::first($state)))
                ->rules(['nullable', 'string', 'max:32']),

            ImportColumn::make('address')
                ->label('Адрес')
                ->exampleHeader('Адрес')
                ->guess(ImportLanguage::COMPANY_HEADERS['address'])
                ->castStateUsing(fn (?string $state): ?string => ImportCell::text($state, 255))
                ->rules(['nullable', 'string', 'max:255']),

            ImportColumn::make('phone')
                ->label('Телефон')
                ->exampleHeader('Телефон')
                ->guess(ImportLanguage::COMPANY_HEADERS['phone'])
                ->castStateUsing(fn (?string $state): ?string => ImportCell::phone($state))
                // Предел тот же, что у колонки: правило свободнее базы
                // роняло загрузку уже на сохранении, без понятной причины
                ->rules(['nullable', 'string', 'max:32']),

            ImportColumn::make('email')
                ->label('Почта')
                ->exampleHeader('Почта')
                ->guess(ImportLanguage::COMPANY_HEADERS['email'])
                ->castStateUsing(fn (?string $state): ?string => ImportCell::email($state))
                ->rules(['nullable', 'email', 'max:190']),

            ImportColumn::make('website')
                ->label('Сайт')
                ->exampleHeader('Сайт')
                ->guess(ImportLanguage::COMPANY_HEADERS['website'])
                ->castStateUsing(fn (?string $state): ?string => ImportCell::first($state, 190))
                ->rules(['nullable', 'string', 'max:190']),

            ImportColumn::make('description')
                ->label('Описание')
                ->exampleHeader('Описание')
                ->guess(ImportLanguage::COMPANY_HEADERS['description'])
                ->castStateUsing(fn (?string $state): ?string => ImportCell::text($state, 5000))
                ->rules(['nullable', 'string', 'max:5000']),

            ImportColumn::make('founded_year')
                ->label('Год основания')
                ->exampleHeader('Год основания')
                ->guess(ImportLanguage::COMPANY_HEADERS['founded_year'])
                // Нижняя граница 1850 отсекала настоящие компании:
                // прядильные и стекольные заводы Европы старше её
                ->castStateUsing(fn (?string $state): ?int => ImportCell::year($state))
                ->rules(['nullable', 'integer', 'between:1500,'.date('Y')]),

            ImportColumn::make('employees_range')
                ->label('Сотрудников')
                ->exampleHeader('Сотрудников')
                ->guess(ImportLanguage::COMPANY_HEADERS['employees_range'])
                ->example('50-100')
                ->castStateUsing(fn (?string $state): ?string => ImportCell::employees($state))
                ->rules(['nullable', 'string', 'max:16']),

            /*
             * Страна — из справочника по названию на любом языке.
             * Без неё загруженная компания не попадает ни в фильтр
             * по стране, ни в счётчик на странице «Страны».
             */
            ImportColumn::make('country_id')
                ->label('Страна')
                ->exampleHeader('Страна')
                ->guess(ImportLanguage::COMPANY_HEADERS['country'])
                ->example('Узбекистан')
                ->castStateUsing(fn (?string $state): ?int => CatalogLookup::countryId(ImportCell::first($state)))
                ->rules(['nullable', 'integer', 'exists:countries,id']),
        ];
    }

    /** @return array<string, list<string>> */
    protected static function headerAliases(): array
    {
        return ImportLanguage::COMPANY_HEADERS;
    }

    /**
     * Код типа компании из справочника по названию на любом языке:
     * «Производитель», «Ishlab chiqaruvchi» и «Manufacturer» — один
     * и тот же manufacturer.
     *
     * Чего нет в справочнике, разбирается по привычным синонимам
     * («trading», «торговая»), а совсем незнакомое значение остаётся
     * как есть: оно всплывёт на карточке и в админке, а не потеряется.
     */
    private static function type(?string $state): ?string
    {
        $needle = ImportLanguage::normalize($state);

        if ($needle === '') {
            return null;
        }

        $type = CompanyType::query()
            ->with('translations')
            ->get()
            ->first(fn (CompanyType $t): bool => ImportLanguage::normalize($t->code) === $needle
                || $t->translations->contains(
                    fn (CompanyTypeTranslation $tr): bool => ImportLanguage::normalize($tr->name) === $needle,
                ));

        return $type?->code ?? CompanyNameStyle::typeKey($state);
    }

    /**
     * Существующая компания находится по ИНН.
     *
     * Без ИНН создаём новую: сопоставлять по названию опасно —
     * одна опечатка порождает дубль, а слияние двух компаний
     * потом делается только руками.
     */
    public function resolveRecord(): ?Company
    {
        $tin = trim((string) ($this->data['tin'] ?? ''));

        if ($tin !== '') {
            return Company::firstOrNew(['tin' => $tin]);
        }

        /*
         * Без ИНН — по названию, но только среди компаний, у которых
         * ИНН тоже нет. Иностранные поставщики приходят без него
         * пачками, и повторная загрузка того же файла удваивала бы
         * базу. Компанию с ИНН безымянная строка не тронет: у неё
         * опознание надёжнее, и подменять её данными по совпадению
         * названия нельзя.
         */
        $name = trim((string) ($this->data['name'] ?? ''));

        if ($name === '') {
            return new Company;
        }

        return Company::query()
            ->whereNull('tin')
            ->where('name', $name)
            ->first() ?? new Company;
    }

    /**
     * Импортированные компании не получают верификацию автоматически.
     *
     * Загруженная база — черновик: пока модератор не проверил,
     * карточка не должна выглядеть проверенной.
     */
    protected function beforeSave(): void
    {
        if (! $this->record->exists) {
            $this->record->status = Company::STATUS_ACTIVE;
            $this->record->verification_level = Company::VERIFICATION_NONE;

            // Карточку завела площадка, а не компания — визитка обязана
            // говорить об этом. Текст правится в админке по компании
            $this->record->source_note ??= 'Данные компании взяты из открытых источников.';
        }
    }

    public static function getCompletedNotificationBody(Import $import): string
    {
        $body = 'Импорт завершён. Обработано строк: '.number_format($import->successful_rows, 0, ',', ' ').'.';

        if (($failed = $import->getFailedRowsCount()) > 0) {
            // Точное число ошибок и файл с причинами: «часть строк
            // не импортирована» не даёт понять, что именно чинить
            $body .= ' Не удалось импортировать: '.number_format($failed, 0, ',', ' ')
                .'. Скачайте файл с ошибками — в нём причина по каждой строке.';
        }

        return $body;
    }
}
