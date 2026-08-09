<?php

declare(strict_types=1);

namespace App\Http\Controllers\Public;

use App\Http\Controllers\Controller;
use App\Models\Company;
use App\Models\Listing;
use App\Services\ContactUnlockService;
use Illuminate\Http\RedirectResponse;
use Illuminate\Http\Request;

/**
 * Раскрытие контактов компании.
 *
 * Отдельный маршрут, а не действие внутри карточки: раскрыть контакт
 * можно и с визитки, и из карточки объявления, и оба пути должны
 * приводить к одной и той же операции.
 */
class ContactUnlockController extends Controller
{
    public function __construct(private readonly ContactUnlockService $service) {}

    public function store(Request $request, string $slug): RedirectResponse
    {
        $target = Company::query()->where('slug', $slug)->firstOrFail();

        $listing = null;

        if ($request->filled('listing_id')) {
            // Объявление нужно только для отчётности «откуда пришёл
            // интерес»: чужое или несуществующее просто игнорируем,
            // отказывать в раскрытии из-за него неправильно
            $listing = Listing::query()
                ->where('company_id', $target->id)
                ->find($request->integer('listing_id'));
        }

        $result = $this->service->unlock($request->user(), $target, $listing);

        return back()->with($result['ok'] ? 'success' : 'error', $result['message']);
    }
}
