<?php

declare(strict_types=1);

namespace App\Http\Controllers\Cabinet;

use App\Http\Controllers\Controller;
use App\Models\Category;
use App\Models\Listing;
use App\Support\Notifier;
use Illuminate\Http\JsonResponse;
use Illuminate\Http\RedirectResponse;
use Illuminate\Http\Request;
use Illuminate\Validation\ValidationException;
use Inertia\Inertia;
use Inertia\Response;

/**
 * Мастер создания и редактирования объявления.
 *
 * Черновик существует в базе с первого шага: автосохранение обещано
 * в интерфейсе, а сохранять некуда, пока записи нет. Обратная сторона —
 * брошенные черновики, поэтому они не попадают ни в выдачу, ни в лимит
 * активных объявлений.
 */
class ListingWizardController extends Controller
{
    public function create(Request $request): RedirectResponse|Response
    {
        $company = $request->user()->company;

        if ($company === null) {
            return redirect()->route('cabinet.company')
                ->with('warning', 'Сначала заполните данные компании — объявление публикуется от её имени');
        }

        // Лимит тарифа считается по активным: черновики не занимают слот
        $plan = $company->plan();
        $active = $company->activeListings()->count();

        if ($plan->listings_limit !== null && $active >= $plan->listings_limit) {
            return redirect()->route('cabinet.listings')->with(
                'error',
                "Достигнут лимит тарифа {$plan->name}: {$plan->listings_limit} активных объявлений. Снимите ненужное или смените тариф.",
            );
        }

        /*
         * Незаполненный черновик переиспользуется.
         *
         * Раньше каждый заход на эту страницу создавал новую строку —
         * а это GET: его дёргает предзагрузка ссылок в браузере, обход
         * краулером и обычное обновление страницы. За неделю у активного
         * пользователя накапливались десятки пустых черновиков.
         */
        $draft = $company->listings()
            ->where('status', Listing::STATUS_DRAFT)
            ->where('title', '')
            ->whereNull('description')
            ->latest()
            ->first();

        $listing = $draft ?? $company->listings()->create([
            'user_id' => $request->user()->id,
            'city_id' => $company->city_id,
            'status' => Listing::STATUS_DRAFT,
            'type' => Listing::TYPE_SUPPLY,
            'title' => '',
            'currency' => 'UZS',
            'wizard_step' => 1,
        ]);

        return redirect()->route('cabinet.listings.edit', $listing->id);
    }

    public function edit(Request $request, int $id): Response
    {
        $listing = $this->owned($request, $id);

        return Inertia::render('cabinet/listings/Wizard', [
            'listing' => [
                'id' => $listing->id,
                'type' => $listing->type,
                'category_id' => $listing->category_id,
                'parent_id' => $listing->category?->parent_id,
                'title' => $listing->title,
                'description' => $listing->description,
                'price' => $listing->price !== null ? (float) $listing->price : null,
                'currency' => $listing->currency,
                'unit' => $listing->unit,
                'price_negotiable' => $listing->price_negotiable,
                'min_order' => $listing->min_order,
                'delivery_terms' => $listing->delivery_terms,
                'payment_terms' => $listing->payment_terms,
                'status' => $listing->status,
                'step' => $listing->wizard_step,
                'attributes' => $listing->attributes()->pluck('value', 'key'),
                'images' => $listing->images()->orderBy('sort')->get()
                    ->map(fn ($i): array => ['id' => $i->id, 'thumb' => $i->thumbUrl()])
                    ->values(),
            ],
            'categories' => $this->categoryTree(),
            'slots' => $this->slots($request),
        ]);
    }

    /**
     * Автосохранение черновика.
     *
     * Отвечает JSON, а не редиректом: страница не должна дёргаться
     * каждые двадцать секунд. Валидация здесь мягкая — человек ещё
     * печатает, и ругаться на незаполненное посреди набора нельзя.
     */
    public function autosave(Request $request, int $id): JsonResponse
    {
        $listing = $this->owned($request, $id);

        $data = $request->validate([
            'type' => ['nullable', 'in:supply,demand'],
            'category_id' => ['nullable', 'exists:categories,id'],
            'title' => ['nullable', 'string', 'max:90'],
            'description' => ['nullable', 'string', 'max:5000'],
            'price' => ['nullable', 'numeric', 'min:0', 'max:99999999999'],
            'currency' => ['nullable', 'in:UZS,USD'],
            'unit' => ['nullable', 'string', 'max:20'],
            'price_negotiable' => ['nullable', 'boolean'],
            'min_order' => ['nullable', 'integer', 'min:0'],
            'delivery_terms' => ['nullable', 'string', 'max:500'],
            'payment_terms' => ['nullable', 'string', 'max:500'],
            'step' => ['nullable', 'integer', 'between:1,4'],
            'attributes' => ['nullable', 'array'],
        ]);

        $attributes = $data['attributes'] ?? [];
        unset($data['attributes']);

        if (isset($data['step'])) {
            $data['wizard_step'] = $data['step'];
            unset($data['step']);
        }

        $listing->fill(array_filter($data, fn ($v): bool => $v !== null));

        // Отдельно: false — валидное значение, array_filter его выбрасывает
        if ($request->has('price_negotiable')) {
            $listing->price_negotiable = $request->boolean('price_negotiable');
        }

        $listing->save();

        foreach ($attributes as $key => $value) {
            $listing->attributes()->updateOrCreate(['key' => $key], ['value' => (string) $value]);
        }

        return response()->json(['saved_at' => now()->toIso8601String()]);
    }

    /**
     * Публикация. Здесь проверка строгая: то, что можно было отложить
     * в черновике, обязано быть заполнено перед показом покупателям.
     */
    public function publish(Request $request, int $id): RedirectResponse
    {
        $listing = $this->owned($request, $id);

        $request->validate([
            'category_id' => ['required', 'exists:categories,id'],
            'title' => ['required', 'string', 'min:10', 'max:90'],
            'description' => ['required', 'string', 'min:30', 'max:5000'],
            'price' => ['nullable', 'numeric', 'min:0'],
            'price_negotiable' => ['boolean'],
        ], [
            'category_id.required' => 'Выберите категорию — без неё объявление не найдут',
            'title.required' => 'Укажите заголовок',
            'title.min' => 'Заголовок слишком короткий: укажите товар, марку и объём',
            'description.required' => 'Добавьте описание',
            'description.min' => 'Описание слишком короткое — расскажите об условиях и объёмах',
        ]);

        if (! $request->boolean('price_negotiable') && $request->input('price') === null) {
            throw ValidationException::withMessages([
                'price' => 'Укажите цену или отметьте «цена договорная»',
            ]);
        }

        $company = $listing->company;
        $plan = $company->plan();
        $active = $company->activeListings()->where('id', '!=', $listing->id)->count();

        if ($plan->listings_limit !== null && $active >= $plan->listings_limit) {
            return back()->with('error', "Достигнут лимит тарифа {$plan->name}: {$plan->listings_limit} активных объявлений.");
        }

        $listing->fill($request->only([
            'category_id', 'title', 'description', 'price', 'currency',
            'unit', 'min_order', 'delivery_terms', 'payment_terms',
        ]));

        /*
         * Сразу на витрину, без предварительной модерации: ожидание
         * проверки отпугивало продавцов сильнее, чем редкий спам вредил
         * покупателям. Контроль остаётся постмодерацией — модератор
         * в любой момент снимает опубликованное с указанием причины.
         */
        $listing->price_negotiable = $request->boolean('price_negotiable');
        $listing->status = Listing::STATUS_ACTIVE;
        $listing->wizard_step = 4;
        $listing->published_at = now();
        $listing->expires_at = now()->addDays(Listing::LIFETIME_DAYS);
        $listing->save();

        if (blank($listing->slug)) {
            $listing->slug = Listing::makeSlug($listing->title, $listing->id);
            $listing->save();
        }

        app(Notifier::class)->company(
            $company,
            'moderation',
            "Объявление «{$listing->title}» опубликовано и видно покупателям",
            ['tone' => 'success', 'url' => route('cabinet.listings')],
        );

        return redirect()->route('cabinet.listings')
            ->with('success', 'Объявление опубликовано — покупатели уже видят его в каталоге.');
    }

    /**
     * Дерево категорий с полями подкатегорий.
     *
     * @return list<array<string, mixed>>
     */
    private function categoryTree(): array
    {
        return Category::query()
            ->whereNull('parent_id')
            ->where('is_active', true)
            ->with(['translations', 'children.translations', 'children.fields'])
            ->orderBy('sort')
            ->get()
            ->map(fn (Category $parent): array => [
                'id' => $parent->id,
                'slug' => $parent->slug,
                'name' => $parent->name(),
                'children' => $parent->children->map(fn (Category $child): array => [
                    'id' => $child->id,
                    'name' => $child->name(),
                    'fields' => $child->fields->map(fn ($f): array => [
                        'key' => $f->key,
                        'label' => $f->label,
                        'type' => $f->type,
                        'options' => $f->options ?? [],
                        'unit' => $f->unit,
                    ]),
                ]),
            ])
            ->all();
    }

    /** @return array{used: int, total: int|null} */
    private function slots(Request $request): array
    {
        $company = $request->user()->company;
        $plan = $company?->plan();

        return [
            'used' => $company?->activeListings()->count() ?? 0,
            'total' => $plan?->listings_limit,
        ];
    }

    private function owned(Request $request, int $id): Listing
    {
        $company = $request->user()->company;

        abort_if($company === null, 404);

        $listing = $company->listings()->with(['category', 'attributes', 'images'])->find($id);

        abort_if($listing === null, 404);

        return $listing;
    }
}
