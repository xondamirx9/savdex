<?php

declare(strict_types=1);

namespace App\Http\Middleware;

use App\Support\Locales;
use Closure;
use Illuminate\Http\Request;
use Illuminate\Support\Str;
use Inertia\Middleware;

/**
 * Данные, доступные на каждой странице без явной передачи из контроллера.
 * Держим набор минимальным: всё, что попадает сюда, сериализуется
 * в HTML при каждом запросе.
 */
class HandleInertiaRequests extends Middleware
{
    protected $rootView = 'app';

    public function version(Request $request): ?string
    {
        return parent::version($request);
    }

    /**
     * Адрес страницы для Inertia — с языковым префиксом.
     *
     * LocalizeUrl снимает префикс до маршрутизации, поэтому штатный
     * резолвер видел бы уже «очищенный» адрес: человек открывал
     * /uz/companies, а Inertia при гидрации записывала /companies
     * в строку браузера — скопированная оттуда ссылка открывалась
     * не на том языке, а после редиректа на сохранённый язык адрес
     * выглядел так, будто переключение не сработало.
     */
    public function urlResolver(): Closure
    {
        return function (Request $request): string {
            $prefix = Locales::prefix(app()->getLocale());
            $uri = Str::start(Str::after($request->fullUrl(), $request->getSchemeAndHttpHost()), '/');

            return $uri === '/' && $prefix !== '' ? $prefix : $prefix.$uri;
        };
    }

    /**
     * @return array<string, mixed>
     */
    public function share(Request $request): array
    {
        $user = $request->user();

        return [
            ...parent::share($request),

            'auth' => [
                'user' => $user ? [
                    'id' => $user->id,
                    'name' => $user->name,
                    'email' => $user->email,
                    'locale' => $user->locale,
                    'email_verified' => $user->hasVerifiedEmail(),
                    'must_change_password' => $user->must_change_password,
                    // Пункт «Управление» в меню — только администраторам
                    'is_admin' => (bool) $user->is_admin,
                ] : null,

                'company' => $user?->company ? [
                    'id' => $user->company->id,
                    'name' => $user->company->name,
                    'slug' => $user->company->slug,
                    'verification_level' => $user->company->verification_level,
                    'profile_completeness' => $user->company->profileCompleteness(),
                ] : null,
            ],

            /*
             * Остаток на раскрытие контактов для счётчика в шапке.
             *
             * Считается лениво: на публичных страницах гостю он не нужен.
             *
             * Раньше шапка читала auth.credits, которого никто не клал
             * в общие пропсы, — и всем показывала «0 кредитов». Человек
             * на платном тарифе с полусотней контактов в месяц видел ноль
             * и делал вывод, что открыть ничего не может.
             *
             * Имя contactsLeft, а не wallet: страницы биллинга и визитки
             * отдают собственный проп wallet со своей формой. Проп
             * страницы перекрывает общий — та же ловушка, из-за которой
             * колокольчик пришлось назвать bell, а не notifications.
             */
            'contactsLeft' => fn () => $this->walletSummary($request),

            /*
             * Избранное: список id для сердечек на карточках и счётчик
             * для шапки. Лениво и только id — сами карточки нужны лишь
             * на странице /favorites, а сердечки должны знать одно:
             * закрашивать себя или нет.
             */
            'favorites' => fn () => $user === null
                ? []
                : \App\Models\Favorite::query()
                    ->where('user_id', $user->id)
                    ->pluck('listing_id'),

            'flash' => [
                'success' => fn () => $request->session()->get('success'),
                'error' => fn () => $request->session()->get('error'),
                'warning' => fn () => $request->session()->get('warning'),
            ],

            /*
             * Счётчики у пунктов меню кабинета. Замыкание вычисляется
             * лениво — на публичных страницах эти запросы не выполняются.
             */
            'counts' => fn () => $this->cabinetCounts($request),

            /*
             * Последние уведомления для колокольчика. Пять штук: больше
             * в выпадающий блок не помещается, а полный список открывается
             * отдельной страницей.
             *
             * Имя bell, а не notifications: страница /notifications отдаёт
             * свой проп с таким именем — список записей. Проп страницы
             * перекрывает общий, и шапка получала массив вместо объекта,
             * падая на latest.map. Экран при этом оставался пустым:
             * ошибка внутри React рушит всё дерево, а не одну шапку.
             */
            'bell' => fn () => $user === null ? null : [
                'unread' => $user->alerts()->unread()->count(),
                'latest' => $user->alerts()->limit(5)->get()
                    ->map(fn ($n): array => [
                        'id' => $n->id,
                        'type' => $n->type,
                        'tone' => $n->tone,
                        'title' => $n->title,
                        'read' => $n->read_at !== null,
                        'ago' => $n->created_at->diffForHumans(),
                    ]),
            ],

            /*
             * Разделы каталога для выпадающего списка поиска в шапке.
             * Их шесть, и запрос дешёвый; появится нагрузка — закэшируем
             * со сбросом при записи, как и счётчики витрины.
             */
            'navCategories' => fn () => \App\Models\Category::query()
                ->whereNull('parent_id')
                ->where('is_active', true)
                ->with('translations')
                ->orderBy('sort')
                ->get()
                ->map(fn ($c): array => ['id' => $c->id, 'name' => $c->name()])
                ->values(),

            'locale' => app()->getLocale(),

            /*
             * Словарь интерфейса.
             *
             * Только при полной загрузке страницы: переходы Inertia
             * идут XHR-ом, словарь у браузера к этому моменту уже есть,
             * и присылать полторы тысячи фраз на каждый клик значит
             * тратить чужой мобильный трафик впустую.
             *
             * Смена языка — обычная ссылка с перезагрузкой, поэтому
             * новый словарь приходит вместе с новой страницей.
             */
            'translations' => $request->hasHeader('X-Inertia') ? null : trans('ui'),

            /*
             * Адреса этой же страницы на других языках.
             *
             * Считает сервер, а не переключатель в браузере: те же
             * адреса нужны для hreflang, и собирать их дважды по разным
             * правилам — верный способ получить расхождение.
             */
            'localeLinks' => $this->localeLinks($request),

            /*
             * Язык, который стоит предложить, — по настройкам браузера.
             * Именно предложить: автоматический перенос по этому
             * признаку уводил бы поисковых роботов на английскую
             * версию, а посетителя — со страницы, которую ему прислали.
             */
            'localeSuggest' => SetLocale::suggest($request),
        ];
    }

    /**
     * @return list<array{code: string, label: string, short: string, url: string}>
     */
    private function localeLinks(Request $request): array
    {
        $path = $request->getRequestUri();

        return array_map(fn (string $code): array => [
            'code' => $code,
            'label' => Locales::ALL[$code]['label'],
            'short' => Locales::ALL[$code]['short'],
            'url' => Locales::switchUrl($path, $code),
        ], Locales::codes());
    }

    /**
     * Сколько контактов компания может открыть прямо сейчас.
     *
     * Порядок расхода — сначала месячный лимит тарифа, потом кредиты
     * (см. ContactUnlockService), поэтому в шапке имеет смысл общая
     * цифра: человек спрашивает «сколько я могу открыть», а не «сколько
     * у меня кредитов». Разбивка отдаётся отдельно — для подсказки.
     *
     * plan_left = null означает безлимитный тариф, а не ноль.
     *
     * @return array{plan_left: int|null, credits: int, total: int|null, resets_at: string|null}|null
     */
    private function walletSummary(Request $request): ?array
    {
        $company = $request->user()?->company;

        if ($company === null) {
            return null;
        }

        $plan = $company->plan();
        $wallet = $company->wallet;
        $credits = $wallet?->credits ?? 0;

        $planLeft = $plan->contacts_limit === null
            ? null
            : max(0, $plan->contacts_limit - ($wallet?->contacts_used_this_period ?? 0));

        return [
            'plan_left' => $planLeft,
            'credits' => $credits,
            'total' => $planLeft === null ? null : $planLeft + $credits,
            'resets_at' => $wallet?->period_resets_at?->translatedFormat('d.m.Y'),
        ];
    }

    /**
     * Счётчики разделов кабинета.
     *
     * Считаются только внутри кабинета: на витрине они не нужны,
     * а четыре COUNT на каждый переход по каталогу — лишняя работа.
     *
     * @return array<string, int>|null
     */
    private function cabinetCounts(Request $request): ?array
    {
        $company = $request->user()?->company;

        if ($company === null || ! $request->is('cabinet', 'cabinet/*')) {
            return null;
        }

        return [
            'listings' => $company->activeListings()->count(),
            'contacts' => $company->unlocks()->count(),
            'incoming' => $company->unlockedBy()->count(),
            'reviews' => $company->reviews()->count(),
        ];
    }
}
