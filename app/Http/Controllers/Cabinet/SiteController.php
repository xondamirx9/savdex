<?php

declare(strict_types=1);

namespace App\Http\Controllers\Cabinet;

use App\Http\Controllers\Controller;
use App\Models\Company;
use App\Models\CompanySite;
use App\Models\CompanySiteProduct;
use App\Support\Currencies;
use App\Support\ImageStore;
use App\Support\Microsite\SiteHost;
use App\Support\Microsite\SitePage;
use App\Support\Microsite\SiteTheme;
use Closure;
use Illuminate\Http\RedirectResponse;
use Illuminate\Http\Request;
use Illuminate\Validation\Rule;
use Inertia\Inertia;
use Inertia\Response;
use RuntimeException;

/**
 * Редактор мини-сайта: адрес, шаблон и оформление.
 *
 * Сохранение и публикация разделены. Сохранение меняет черновик —
 * его видно только в предпросмотре, — а посетители видят прежний
 * вид, пока компания не нажмёт «Опубликовать».
 *
 * Открыть редактор можно на любом тарифе: компания должна видеть,
 * что получит, до покупки. Сохранять и публиковать — только на
 * тарифе с мини-сайтом.
 */
class SiteController extends Controller
{
    public function edit(Request $request): Response|RedirectResponse
    {
        $company = $request->user()->company;

        if ($company === null) {
            return redirect()->route('cabinet.company');
        }

        $site = $company->site;

        return Inertia::render('cabinet/Site', [
            'available' => $this->available($company),
            'address' => SiteHost::addressParts(),
            'site' => $site === null ? null : [
                'subdomain' => $site->subdomain,
                'url' => $site->url(),
                'status' => $site->status,
                'published_at' => $site->published_at?->translatedFormat('d.m.Y H:i'),
                'unpublished_changes' => $site->hasUnpublishedChanges(),
            ],
            'subdomain' => $site->subdomain ?? SiteHost::suggest($company->slug),
            'theme' => $site?->draftTheme() ?? SiteTheme::normalize(null),
            'hero_url' => $site !== null ? CompanySite::heroUrl($site->draftTheme()) : null,
            'options' => SiteTheme::options(),

            'products' => $company->siteProducts()->get()->map(fn (CompanySiteProduct $p): array => [
                'id' => $p->id,
                'title' => $p->title,
                'description' => $p->description,
                'price' => $p->price !== null ? (float) $p->price : null,
                'currency' => $p->currency,
                'unit' => $p->unit,
                'image' => $p->thumbUrl(),
            ])->values(),
            'products_limit' => CompanySiteProduct::LIMIT,
            // Объявления попадают на сайт сами — редактор только говорит сколько
            'listings_count' => $company->activeListings()->count(),
            'currencies' => Currencies::codes(),
        ]);
    }

    public function update(Request $request): RedirectResponse
    {
        $company = $request->user()->company;

        if ($company === null || ! $this->available($company)) {
            return back()->with('error', __('ui.messages.site.plan_required'));
        }

        $data = $request->validate([
            'subdomain' => $this->subdomainRules($company),
            ...SiteTheme::rules(),
        ], [
            'subdomain.regex' => __('ui.messages.site.subdomain_format'),
            'subdomain.unique' => __('ui.messages.site.subdomain_taken'),
        ]);

        // Фон меняется только загрузкой: из формы он не принимается,
        // иначе в тему можно было бы подставить чужой файл
        // Запросом, а не через связь: закэшированный пустой site
        // остался бы на компании после создания сайта ниже
        $hero = $company->site()->first()?->theme['hero_image'] ?? null;

        CompanySite::updateOrCreate(
            ['company_id' => $company->id],
            [
                'subdomain' => strtolower($data['subdomain']),
                'theme' => SiteTheme::normalize([...$data['theme'], 'hero_image' => $hero]),
            ],
        );

        return back()->with('success', __('ui.messages.site.saved'));
    }

    public function publish(Request $request): RedirectResponse
    {
        $company = $request->user()->company;

        if ($company === null || ! $this->available($company)) {
            return back()->with('error', __('ui.messages.site.plan_required'));
        }

        $site = $company->site;

        // Публикуется сохранённое: адреса ещё нет, пока черновик
        // не сохранён хотя бы раз
        if ($site === null) {
            return back()->with('error', __('ui.messages.site.save_first'));
        }

        $site->publish();

        return back()->with('success', __('ui.messages.site.published'));
    }

    /**
     * Фон первого экрана. Попадает в черновик: посетители увидят его
     * после «Опубликовать», как и остальное оформление.
     */
    public function uploadHero(Request $request): RedirectResponse
    {
        $company = $request->user()->company;

        if ($company === null || ! $this->available($company)) {
            return back()->with('error', __('ui.messages.site.plan_required'));
        }

        $site = $company->site;

        if ($site === null) {
            return back()->with('error', __('ui.messages.site.save_first'));
        }

        $request->validate([
            'hero' => ['required', 'file', 'mimes:'.implode(',', ImageStore::ALLOWED_MIMES), 'max:'.ImageStore::MAX_SIZE_KB],
        ], [
            'hero.required' => __('ui.messages.file.required'),
            'hero.mimes' => __('ui.messages.image.mimes'),
            'hero.max' => __('ui.messages.image.max'),
        ]);

        $store = app(ImageStore::class);

        try {
            $path = $store->store($request->file('hero'), "sites/{$company->id}", ImageStore::COVER);
        } catch (RuntimeException) {
            return back()->with('error', __('ui.messages.image.unreadable'));
        }

        $this->replaceHero($site, $path);

        return back()->with('success', __('ui.messages.site.hero_saved'));
    }

    public function removeHero(Request $request): RedirectResponse
    {
        $site = $request->user()->company?->site;

        if ($site !== null) {
            $this->replaceHero($site, null);
        }

        return back()->with('success', __('ui.messages.site.hero_removed'));
    }

    /** Новый фон черновика; прежний файл удаляется, если он не на сайте. */
    private function replaceHero(CompanySite $site, ?string $path): void
    {
        $previous = $site->theme['hero_image'] ?? null;

        $site->forceFill(['theme' => [...$site->draftTheme(), 'hero_image' => $path]])->save();

        if ($previous !== null && ! $site->heroInUse($previous)) {
            app(ImageStore::class)->delete($previous);
        }
    }

    /** Снять с публикации можно и без тарифа: это не услуга, а отказ от неё. */
    public function unpublish(Request $request): RedirectResponse
    {
        $request->user()->company?->site?->unpublish();

        return back()->with('success', __('ui.messages.site.unpublished'));
    }

    /**
     * Предпросмотр для редактора — в iframe.
     *
     * Оформление приходит параметром theme: редактор присылает его на
     * каждое изменение, и страница перекрашивается без сохранения.
     * Параметр проходит normalize(), как и всё остальное снаружи.
     * Без параметра показывается сохранённый черновик.
     */
    public function preview(Request $request): Response|RedirectResponse
    {
        $company = $request->user()->company;

        if ($company === null) {
            return redirect()->route('cabinet.company');
        }

        $site = $company->site ?? new CompanySite([
            'company_id' => $company->id,
            'subdomain' => SiteHost::suggest($company->slug),
        ]);
        $site->setRelation('company', $company);

        $fromEditor = json_decode((string) $request->query('theme', ''), true);

        $theme = is_array($fromEditor)
            ? SiteTheme::normalize($fromEditor)
            : $site->draftTheme();

        return SitePage::render($site, $theme, preview: true);
    }

    private function available(Company $company): bool
    {
        return ! $company->isBlocked() && (bool) $company->plan()->has_microsite;
    }

    /** @return list<mixed> */
    private function subdomainRules(Company $company): array
    {
        return [
            'required', 'string', 'lowercase', 'regex:'.SiteHost::PATTERN,
            function (string $attribute, mixed $value, Closure $fail): void {
                if (SiteHost::isReserved((string) $value)) {
                    $fail(__('ui.messages.site.subdomain_reserved'));
                }
            },
            Rule::unique('company_sites', 'subdomain')->ignore($company->id, 'company_id'),
        ];
    }
}
