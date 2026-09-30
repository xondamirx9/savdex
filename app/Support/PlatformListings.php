<?php

declare(strict_types=1);

namespace App\Support;

use App\Models\Company;
use App\Models\Listing;
use Illuminate\Database\Eloquent\Builder;

/**
 * Заявки площадки: загруженные из Excel без компании и лежащие у
 * служебной компании (Anjir Group), пока не найден настоящий владелец.
 *
 * На витрине они подписаны площадкой SavdEx: служебная компания не
 * продаёт и не покупает, показывать её продавцом — вводить в заблуждение.
 * Отклики на них приходят в её кабинет. Собственные объявления этой
 * компании, написанные в кабинете, — обычные.
 *
 * Та же проверка у Django — savdex/web/platform.py.
 */
final class PlatformListings
{
    /** Как подписана заявка площадки вместо компании. */
    public const NAME = 'SavdEx';

    /** Служебная компания по умолчанию — по названию. */
    private const DEFAULT_NAME = 'anjir group';

    public static function companyId(): ?int
    {
        return once(function (): ?int {
            $configured = trim((string) config('app.service_company'));

            if ($configured !== '') {
                $id = Company::query()
                    ->where(fn (Builder $q) => $q
                        ->when(ctype_digit($configured), fn (Builder $q) => $q->where('id', (int) $configured))
                        ->orWhere('tin', $configured)
                        ->orWhere('name', $configured))
                    ->orderBy('id')
                    ->value('id');

                return $id !== null ? (int) $id : null;
            }

            $id = Company::query()
                ->whereRaw('lower(name) like ?', ['%'.self::DEFAULT_NAME.'%'])
                ->orderBy('id')
                ->value('id');

            return $id !== null ? (int) $id : null;
        });
    }

    public static function owns(Listing $listing): bool
    {
        $service = self::companyId();

        return $service !== null
            && $listing->company_id === $service
            && $listing->source === Listing::SOURCE_IMPORT;
    }

    /** Без заявок площадки — для страницы и мини-сайта служебной компании. */
    public static function exclude(Builder $query): Builder
    {
        $service = self::companyId();

        return $service === null
            ? $query
            : $query->where(fn (Builder $q) => $q
                ->where('company_id', '!=', $service)
                ->orWhere('source', '!=', Listing::SOURCE_IMPORT)
                ->orWhereNull('source'));
    }
}
