<?php

declare(strict_types=1);

namespace App\Http\Controllers\Public;

use App\Http\Controllers\Controller;
use App\Models\Company;
use App\Models\CompanyContact;
use App\Models\CompanyDocument;
use App\Models\Country;
use App\Models\Review;
use App\Services\ReviewService;
use App\Support\DateHelper;
use App\Support\SearchText;
use App\Support\SeoBuilders;
use App\Support\StatsRecorder;
use Illuminate\Database\Eloquent\Builder;
use Illuminate\Http\Request;
use Inertia\Inertia;
use Inertia\Response;

class CompanyController extends Controller
{
    /** Каталог компаний с фильтрами (§5.5 FR-CAT-00). */
    public function index(Request $request): Response
    {
        $companies = $this->filtered($request)
            ->with(['city.translations', 'country'])
            // Для процента заполненности: наличие одобренных документов
            // подзапросом, а не отдельным запросом на каждую карточку
            ->withExists(['documents as has_approved_documents' => fn ($d) => $d->where('moderation_status', 'approved')])
            ->orderByDesc('verification_level')
            ->orderByDesc('rating')
            /*
             * Уникальный хвост сортировки обязателен: у сотни компаний
             * без проверки и отзывов ключи выше равны, и Postgres тасует
             * их между запросами — одна карточка выпадала на двух
             * страницах подряд, а другая не показывалась вовсе.
             */
            ->orderBy('id')
            ->paginate(12)
            ->withQueryString()
            ->through(fn (Company $c) => [
                'slug' => $c->slug,
                'name' => $c->name,
                'tin' => $c->tin,
                'type' => $c->type,
                'type_label' => $c->typeLabel(),
                'city' => $c->city?->name(),
                'country' => $c->country?->code,
                'verification_level' => $c->verification_level,
                'rating' => (float) $c->rating,
                'reviews_count' => $c->reviews_count,
                // Заполненность профиля вместо «сделок»: сделки площадка
                // не считает, а этот процент — измеримый и честный
                'trust' => $c->profileCompleteness(),
                'created_at' => DateHelper::monthYear($c->created_at),
                'initials' => $c->initials(),
                'logo' => $c->logoUrl(),
                'website' => $c->websiteUrl(),
            ]);

        app(SeoBuilders::class)->companies(
            $companies->total(),
            filtered: $request->hasAny(['q', 'type', 'verified', 'country', 'age']) || $companies->currentPage() > 1,
        );

        return Inertia::render('companies/Index', [
            'companies' => $companies,
            'filters' => $request->only(['q', 'type', 'verified', 'country', 'age']),
            'types' => $this->typeOptions($request),
            'countries' => $this->countryOptions($request),
            'facets' => [
                'ages' => $this->ageCounts($request),
                'verified' => $this->filtered($request, 'verified')
                    ->where('verification_level', '>=', Company::VERIFICATION_COMPANY)
                    ->count(),
            ],
            /*
             * «Компаний N, из них проверенных M» — обе цифры об одном
             * и том же наборе. Без условия по статусу проверенных
             * считалось больше, чем компаний всего: заблокированные
             * и ждущие проверки в каталог не попадают, а в счётчик
             * попадали. Заодно запрос ложится на составной индекс
             * (status, verification_level) вместо перебора таблицы.
             */
            'stats' => [
                'total' => Company::where('status', Company::STATUS_ACTIVE)->count(),
                'verified' => Company::where('status', Company::STATUS_ACTIVE)
                    ->where('verification_level', '>=', Company::VERIFICATION_COMPANY)
                    ->count(),
            ],
        ]);
    }

    /**
     * Каталог под выбранными фильтрами.
     *
     * $ignore выключает один фильтр из набора — этим считаются варианты
     * этого же фильтра: сколько компаний найдётся, если переставить
     * переключатель страны, не трогая остальное. Считать по всему
     * каталогу нельзя: цифра рядом со страной обещала бы компании,
     * которых при выбранном типе не существует.
     */
    private function filtered(Request $request, string $ignore = ''): Builder
    {
        $value = fn (string $key): string => $ignore === $key ? '' : $request->string($key)->toString();

        return Company::query()
            ->where('status', Company::STATUS_ACTIVE)
            // Поиск по индексу в обеих графиках: узбекская аудитория
            // набирает латиницей то, что в базе записано кириллицей
            ->when($value('q'), fn ($q, $term) => $q->where(
                fn ($sub) => $sub
                    ->where('search_text', 'like', '%'.SearchText::normalize($term).'%')
                    ->orWhere('tin', 'like', '%'.trim($term).'%'),
            ))
            ->when($value('type'), fn ($q, $type) => $q->where('type', $type))
            // Фильтр по стране — по коду, а не по id: код виден в адресе
            // (/companies?country=uz) и не меняется между окружениями
            ->when($value('country'), fn ($q, $code) => $q->whereHas(
                'country',
                fn ($sub) => $sub->where('code', mb_strtolower($code)),
            ))
            ->when(
                $ignore !== 'verified' && $request->boolean('verified'),
                fn ($q) => $q->where('verification_level', '>=', Company::VERIFICATION_COMPANY),
            )
            ->when($value('age'), fn ($q, $age) => $this->byAge($q, $age));
    }

    /** Возраст компании на площадке: до года, от года до пяти, старше пяти. */
    private function byAge(Builder $query, string $age): Builder
    {
        return match ($age) {
            'lt1' => $query->where('created_at', '>=', now()->subYear()),
            '1to5' => $query->whereBetween('created_at', [now()->subYears(5), now()->subYear()]),
            'gt5' => $query->where('created_at', '<', now()->subYears(5)),
            // Неизвестное значение из адресной строки просто игнорируется
            default => $query,
        };
    }

    /**
     * Типы компаний для фильтра — вместе с числом компаний в каждом.
     *
     * Пустые варианты не предлагаем. Переключатель, который всегда
     * приводит к «по вашему запросу ничего нет», — не фильтр, а тупик:
     * человек листает справочник и на каждом втором шаге упирается
     * в пустую страницу, решая, что сломан сайт. Выбранный вариант
     * остаётся в списке даже опустев — иначе переключатель некуда
     * вернуть.
     *
     * @return list<array{value: string, label: string, count: int}>
     */
    private function typeOptions(Request $request): array
    {
        $counts = $this->filtered($request, 'type')
            ->whereNotNull('type')
            ->selectRaw('type, count(*) as total')
            ->groupBy('type')
            ->pluck('total', 'type');

        $selected = $request->string('type')->toString();

        return collect(Company::typeOptions())
            ->map(fn (string $label, string $value): array => [
                'value' => $value,
                'label' => $label,
                'count' => (int) ($counts[$value] ?? 0),
            ])
            ->filter(fn (array $type): bool => $type['count'] > 0 || $type['value'] === $selected)
            ->values()
            ->all();
    }

    /**
     * Страны для фильтра — только те, где кто-то есть.
     *
     * Справочник держит три десятка стран, а компании пока в немногих:
     * список из справочника обещал венгерские компании и открывал
     * пустую страницу.
     *
     * @return list<array{code: string, name: string, count: int}>
     */
    private function countryOptions(Request $request): array
    {
        $counts = $this->filtered($request, 'country')
            ->whereNotNull('country_id')
            ->selectRaw('country_id, count(*) as total')
            ->groupBy('country_id')
            ->pluck('total', 'country_id');

        $selected = mb_strtolower($request->string('country')->toString());

        return Country::listed()
            ->map(fn (Country $c): array => [
                'code' => $c->code,
                'name' => $c->name(),
                'count' => (int) ($counts[$c->id] ?? 0),
            ])
            ->filter(fn (array $country): bool => $country['count'] > 0 || $country['code'] === $selected)
            ->values()
            ->all();
    }

    /**
     * Сколько компаний в каждой возрастной группе.
     *
     * @return array<string, int>
     */
    private function ageCounts(Request $request): array
    {
        $base = $this->filtered($request, 'age');

        return collect(['lt1', '1to5', 'gt5'])
            ->mapWithKeys(fn (string $age): array => [$age => $this->byAge(clone $base, $age)->count()])
            ->all();
    }

    /**
     * Остаток контактов и кредитов у того, кто смотрит визитку.
     *
     * @return array{contacts_left: int, credits: int}|null
     */
    private function viewerWallet(Request $request, Company $company): ?array
    {
        $viewer = $request->user()?->company;

        if ($viewer === null || $viewer->id === $company->id) {
            return null;
        }

        $plan = $viewer->plan();
        $wallet = $viewer->wallet;

        // null в лимите тарифа — безлимит. Отдаём заведомо большое
        // число, чтобы интерфейс не показывал «осталось 0»
        $left = $plan->contacts_limit === null
            ? PHP_INT_MAX
            : max(0, $plan->contacts_limit - ($wallet?->contacts_used_this_period ?? 0));

        return [
            'contacts_left' => $left,
            'credits' => $wallet?->credits ?? 0,
        ];
    }

    /** Визитка компании (§5.2 FR-COMP-03). */
    public function show(Request $request, string $slug): Response
    {
        $company = Company::query()
            ->with(['city.translations', 'country.translations', 'publicContacts'])
            ->where('slug', $slug)
            ->firstOrFail();

        // «Кто мной интересуется»: авторизованный гость с компанией
        // оставляет след просмотра визитки. Анонимы не записываются
        app(StatsRecorder::class)->companyView($company);

        /*
         * Контакты открыты, если это своя компания либо за неё уже
         * заплачен кредит. Доступ бессрочный: кредит списывается за
         * компанию один раз и навсегда — это обещание на витрине.
         *
         * Обратное направление доступа не даёт: то, что кто-то открыл
         * ваши контакты («кто мной интересуется»), не открывает вам его.
         * Иначе раскрытие работало бы в обе стороны за одну оплату.
         */
        $viewerCompanyId = $request->user()?->company_id;

        $unlocked = $viewerCompanyId !== null && (
            $viewerCompanyId === $company->id
            || $company->unlockedBy()->where('company_id', $viewerCompanyId)->exists()
        );

        $contacts = $company->publicContacts->map(function (CompanyContact $c) use ($unlocked): array {
            // Сайт компании — не способ связи, скрывать его незачем:
            // он и так публичен, а закрытый замком адрес сайта
            // выглядит как жадность и портит доверие
            $alwaysOpen = in_array($c->type, CompanyContact::PUBLIC_TYPES, true);
            $open = $unlocked || $alwaysOpen;

            return [
                'type' => $c->type,
                'label' => $c->label,
                'contact_person' => $c->contact_person,
                'value' => $open ? $c->value : $c->masked(),
                'href' => $open ? $c->href() : null,
                'locked' => ! $open,
            ];
        });

        app(SeoBuilders::class)->company($company);

        return Inertia::render('companies/Show', [
            'company' => $company->businessCard(),
            'initials' => $company->initials(),
            'contacts' => $contacts,

            /*
             * Файлы, которые компания решила показывать. Документы
             * попадают сюда только после одобрения модератором:
             * непроверенная лицензия на визитке — это подтверждение,
             * которого компания не получала.
             */
            'files' => $company->documents()
                ->where('is_public', true)
                ->get()
                // Записи без файла (пропали до переезда на постоянный диск)
                // на визитке не показываются: битая миниатюра — не контент
                ->filter(fn (CompanyDocument $d): bool => $d->isVisibleOnCard() && ! $d->fileMissing())
                ->map(fn (CompanyDocument $d): array => [
                    'id' => $d->id,
                    'title' => $d->title,
                    'type' => $d->type,
                    'is_image' => $d->isImage(),
                    'type_label' => $d->typeLabel(),
                    'size' => $d->sizeLabel(),
                    'is_material' => $d->isMaterial(),
                    'expired' => $d->isExpired(),
                    'valid_until' => $d->valid_until?->translatedFormat('d.m.Y'),
                ])
                ->values(),
            'unlocked' => $unlocked,
            // Свои контакты — не «купленные»: подпись про оплату
            // на собственной визитке выглядит нелепо
            'is_own' => $viewerCompanyId === $company->id,

            /*
             * Отзывы и право их оставить.
             *
             * Причина отказа приходит вместе со страницей, а не в ответ
             * на отправку: человек должен видеть «отзыв можно оставить
             * после раскрытия контактов» до того, как напишет текст.
             */
            'reviews' => $company->reviews()
                ->with('authorCompany')
                ->latest()
                ->limit(20)
                ->get()
                ->map(fn (Review $r): array => [
                    'id' => $r->id,
                    'author' => $r->authorCompany?->name ?? __('ui.cabinet.incoming.deleted'),
                    'initials' => $r->authorCompany?->initials() ?? '?',
                    'rating' => $r->rating,
                    'body' => $r->body,
                    'deal_confirmed' => $r->deal_confirmed,
                    'reply' => $r->reply,
                    'when' => $r->created_at->translatedFormat('d.m.Y'),
                ]),

            'review_blocked' => app(ReviewService::class)->blockedReason($request->user(), $company),
            'criteria' => Review::CRITERIA,

            // Счётчик из базы: на визитке стоял литеральный ноль,
            // и компания с десятком объявлений выглядела пустой
            'listings_count' => $company->activeListings()->visibleIn()->count(),

            /*
             * Остаток на счету покупателя. Нужен, чтобы окно раскрытия
             * показало цену и остаток до нажатия, а не отвечало ошибкой
             * после. Гостю и своей компании не отдаётся.
             */
            'wallet' => $this->viewerWallet($request, $company),
            // Считаем реально скрытые, а не все подряд: счётчик,
            // который врёт на единицу, подрывает доверие ко всей странице
            'locked_count' => $contacts->where('locked', true)->count(),
        ]);
    }
}
