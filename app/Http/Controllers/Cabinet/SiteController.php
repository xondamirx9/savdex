<?php

declare(strict_types=1);

namespace App\Http\Controllers\Cabinet;

use App\Http\Controllers\Controller;
use App\Models\Company;
use App\Models\CompanySite;
use App\Support\Microsite\SiteHost;
use App\Support\Microsite\SitePage;
use App\Support\Microsite\SiteTheme;
use Closure;
use Illuminate\Http\RedirectResponse;
use Illuminate\Http\Request;
use Illuminate\Validation\Rule;
use Inertia\Inertia;
use Inertia\Response;

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
            'options' => SiteTheme::options(),
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

        CompanySite::updateOrCreate(
            ['company_id' => $company->id],
            [
                'subdomain' => strtolower($data['subdomain']),
                'theme' => SiteTheme::normalize($data['theme']),
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
