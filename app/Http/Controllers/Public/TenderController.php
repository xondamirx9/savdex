<?php

declare(strict_types=1);

namespace App\Http\Controllers\Public;

use App\Http\Controllers\Controller;
use App\Models\Category;
use App\Models\Tender;
use App\Support\DateHelper;
use App\Support\Seo;
use Illuminate\Database\Eloquent\Builder;
use Illuminate\Http\Request;
use Illuminate\Support\Str;
use Inertia\Inertia;
use Inertia\Response;

/**
 * Витрина тендеров: список закупок и карточка тендера.
 *
 * Отдельный раздел рядом с каталогом: тендер — это не объявление
 * компании, а закупка внешнего заказчика, которую разместила
 * площадка. По умолчанию показываются открытые (срок подачи не
 * прошёл); завершённые — отдельной вкладкой, чтобы не хоронить
 * актуальные среди старых.
 */
class TenderController extends Controller
{
    private const PER_PAGE = 20;

    public function index(Request $request): Response
    {
        $query = trim($request->string('q')->toString());
        $closed = $request->boolean('closed');
        $categoryId = $request->integer('category');

        $tenders = Tender::query()
            ->with(['category.translations', 'country.translations'])
            ->published()
            ->when(! $closed, fn (Builder $q) => $q->open())
            ->when($closed, fn (Builder $q) => $q->whereNotNull('deadline_at')->where('deadline_at', '<', now()))
            ->when($query !== '', fn (Builder $q) => $q->search($query))
            ->when($categoryId, fn (Builder $q, int $id) => $this->applyCategory($q, $id))
            ->tap(fn (Builder $q) => $closed
                ? $q->orderByDesc('deadline_at')
                : $q->orderByRaw('deadline_at is null, deadline_at asc'))
            ->orderByDesc('published_at')
            ->orderByDesc('id')
            ->paginate(self::PER_PAGE)
            ->withQueryString();

        app(Seo::class)
            ->title(__('ui.tenders.meta_title'))
            ->description(__('ui.tenders.meta_description'))
            ->canonical(url('/tenders'))
            ->noindex($query !== '' || $closed || $tenders->currentPage() > 1);

        return Inertia::render('tenders/Index', [
            'tenders' => $tenders->through(fn (Tender $t): array => $this->card($t)),
            'filters' => [
                'q' => $query,
                'category' => $categoryId ?: null,
                'closed' => $closed,
            ],
            'categories' => $this->categories(),
            'total' => $tenders->total(),
        ]);
    }

    public function show(string $slug): Response
    {
        $tender = Tender::query()
            ->with(['category.translations', 'category.parent.translations', 'country.translations'])
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
                    ['@type' => 'ListItem', 'position' => 1, 'name' => __('ui.tenders.h1'), 'item' => url('/tenders')],
                    ['@type' => 'ListItem', 'position' => 2, 'name' => $tender->localizedTitle(), 'item' => url('/tenders/'.$tender->slug)],
                ],
            ]);

        $similar = Tender::query()
            ->with(['category.translations', 'country.translations'])
            ->published()
            ->open()
            ->where('id', '!=', $tender->id)
            ->when($tender->category_id, fn (Builder $q, int $id) => $q->where('category_id', $id))
            ->orderByRaw('deadline_at is null, deadline_at asc')
            ->limit(3)
            ->get();

        return Inertia::render('tenders/Show', [
            'tender' => $this->full($tender),
            'similar' => $similar->map(fn (Tender $t): array => $this->card($t))->values(),
        ]);
    }

    // ── Представление ────────────────────────────────────────

    /** @return array<string, mixed> */
    private function card(Tender $tender): array
    {
        $daysLeft = $tender->deadline_at !== null
            ? (int) now()->startOfDay()->diffInDays($tender->deadline_at->copy()->startOfDay(), false)
            : null;

        return [
            'id' => $tender->id,
            'slug' => $tender->slug,
            'title' => $tender->localizedTitle(),
            'excerpt' => Str::limit(trim((string) $tender->localizedDescription()), 180),
            'customer' => $tender->customer,
            'category' => $tender->category?->name(),
            'country' => $tender->country?->name(),
            'location' => $tender->location,
            'budget' => $tender->budget !== null ? (float) $tender->budget : null,
            'currency' => $tender->currency,
            'deadline' => DateHelper::dayMonthYear($tender->deadline_at),
            'days_left' => $daysLeft,
            'closed' => $tender->isClosed(),
            'published' => DateHelper::dayMonthYear($tender->published_at),
        ];
    }

    /** @return array<string, mixed> */
    private function full(Tender $tender): array
    {
        return [
            ...$this->card($tender),
            'description' => preg_split('/\R{2,}/u', trim((string) $tender->localizedDescription())) ?: [],
            'source_url' => $tender->source_url,
            'contact_name' => $tender->contact_name,
            'contact_phone' => $tender->contact_phone,
            'contact_email' => $tender->contact_email,
            'parent_category' => $tender->category?->parent?->name(),
        ];
    }

    /** Фильтр по разделу включает его подкатегории. */
    private function applyCategory(Builder $query, int $id): void
    {
        $ids = Category::query()->where('parent_id', $id)->pluck('id')->push($id);

        $query->whereIn('category_id', $ids);
    }

    /** @return list<array<string, mixed>> */
    private function categories(): array
    {
        return Category::query()
            ->whereNull('parent_id')
            ->where('is_active', true)
            ->with(['translations', 'children.translations'])
            ->orderBy('sort')
            ->get()
            ->map(fn (Category $c): array => [
                'id' => $c->id,
                'name' => $c->name(),
                'children' => $c->children->map(fn (Category $child): array => [
                    'id' => $child->id,
                    'name' => $child->name(),
                ])->all(),
            ])
            ->all();
    }
}
