<?php

declare(strict_types=1);

namespace App\Http\Controllers\Public;

use App\Http\Controllers\Controller;
use App\Models\Tender;
use App\Support\Seo;
use App\Support\TenderCard;
use Illuminate\Database\Eloquent\Builder;
use Illuminate\Http\RedirectResponse;
use Illuminate\Http\Request;
use Illuminate\Support\Str;
use Inertia\Inertia;
use Inertia\Response;

/**
 * Карточка тендера.
 *
 * Список закупок живёт в каталоге вкладкой «Тендеры»
 * (CatalogController): человек, пришедший за запросами на закупку,
 * ищет и объявления, и тендеры, а отдельный раздел заставлял его
 * искать дважды. Карточка осталась здесь: у неё свой адрес, который
 * присылают в переписке и знает поисковик.
 */
class TenderController extends Controller
{
    /**
     * Старый адрес раздела — на вкладку каталога.
     *
     * Постоянный редирект: ссылки на /tenders разосланы в переписке
     * и лежат в выдаче поисковика, и 404 на них потерял бы и людей,
     * и накопленный вес страницы. Отборы переезжают вместе с адресом.
     */
    public function index(Request $request): RedirectResponse
    {
        $query = array_filter([
            'type' => 'tender',
            'q' => trim($request->string('q')->toString()),
            'category' => $request->integer('category') ?: null,
            'closed' => $request->boolean('closed') ? 1 : null,
        ], fn (mixed $v): bool => $v !== null && $v !== '');

        return redirect()->to('/catalog?'.http_build_query($query), 301);
    }

    public function show(string $slug): Response
    {
        $tender = Tender::query()
            ->with([...TenderCard::relations(), 'category.parent.translations'])
            ->published()
            ->where('slug', $slug)
            ->firstOrFail();

        $tender->increment('views_count');

        $description = Str::limit((string) $tender->localizedDescription(), 160);

        app(Seo::class)
            ->title($tender->localizedTitle())
            ->description($description !== '' ? $description : null)
            ->canonical(url('/tenders/'.$tender->slug))
            ->schema([
                '@type' => 'BreadcrumbList',
                'itemListElement' => [
                    ['@type' => 'ListItem', 'position' => 1, 'name' => __('ui.tenders.h1'), 'item' => url('/catalog').'?type=tender'],
                    ['@type' => 'ListItem', 'position' => 2, 'name' => $tender->localizedTitle(), 'item' => url('/tenders/'.$tender->slug)],
                ],
            ]);

        $similar = Tender::query()
            ->with(TenderCard::relations())
            ->published()
            ->open()
            ->where('id', '!=', $tender->id)
            ->when($tender->category_id, fn (Builder $q, int $id) => $q->where('category_id', $id))
            ->orderByRaw('deadline_at is null, deadline_at asc')
            ->limit(3)
            ->get();

        return Inertia::render('tenders/Show', [
            'tender' => $this->full($tender),
            'similar' => $similar->map(fn (Tender $t): array => TenderCard::present($t))->values(),
        ]);
    }

    /** @return array<string, mixed> */
    private function full(Tender $tender): array
    {
        return [
            ...TenderCard::present($tender),
            'description' => preg_split('/\R{2,}/u', trim((string) $tender->localizedDescription())) ?: [],
            'source_url' => $tender->source_url,
            'contact_name' => $tender->contact_name,
            'contact_phone' => $tender->contact_phone,
            'contact_email' => $tender->contact_email,
            'parent_category' => $tender->category?->parent?->name(),
        ];
    }
}
