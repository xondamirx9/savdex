<?php

declare(strict_types=1);

namespace App\Http\Controllers\Microsite;

use App\Http\Controllers\Controller;
use App\Models\CompanySite;
use App\Support\Microsite\SiteHost;
use App\Support\Microsite\SitePage;
use Illuminate\Http\RedirectResponse;
use Inertia\Response;

/**
 * Мини-сайты компаний: savdex.uz/s/acme или acme.savdex.site.
 *
 * Сайт, которого нет, и сайт, который выключен, — одинаковые 404:
 * снятый с публикации или оставшийся без тарифа сайт не должен
 * сообщать посторонним, что компания с таким адресом существует.
 */
class SiteController extends Controller
{
    /** Поддомен: acme.savdex.site. */
    public function show(string $subdomain): Response
    {
        $site = $this->live($subdomain);

        return SitePage::render($site, $site->publishedTheme());
    }

    /** Страница площадки: savdex.uz/s/acme. */
    public function page(string $subdomain): Response|RedirectResponse
    {
        $site = $this->live($subdomain);

        if (SiteHost::usesSubdomains()) {
            return redirect()->away($site->url(), 301);
        }

        return SitePage::render($site, $site->publishedTheme());
    }

    private function live(string $subdomain): CompanySite
    {
        $site = CompanySite::query()
            ->with('company')
            ->where('subdomain', strtolower($subdomain))
            ->first();

        abort_unless($site?->isLive() ?? false, 404);

        return $site;
    }

    /**
     * Сам savdex.site без поддомена своей страницы не имеет —
     * ведёт в каталог компаний площадки.
     */
    public function root(): RedirectResponse
    {
        return redirect()->away(rtrim((string) config('app.url'), '/').'/companies');
    }
}
