<?php

declare(strict_types=1);

namespace App\Http\Controllers\Auth;

use App\Http\Controllers\Controller;
use App\Models\Category;
use App\Models\City;
use App\Models\Company;
use App\Models\Country;
use App\Rules\Tin;
use Illuminate\Http\RedirectResponse;
use Illuminate\Http\Request;
use Illuminate\Validation\Rule;
use Inertia\Inertia;
use Inertia\Response;

/**
 * Второй шаг регистрации — данные компании.
 *
 * Отдельным экраном, а не полями в общей форме: восемь дополнительных
 * полей в форме регистрации заметно снижают долю дошедших до конца.
 * Здесь же есть «заполнить позже» — аккаунт уже создан, и терять
 * человека из-за незаполненного ИНН нельзя.
 *
 * Юрлицо приходит сюда с уже заведённой компанией: название, ИНН
 * и категории указаны при регистрации, шаг дополняет её типом,
 * страной, городом и ролью. Физлицо и фрилансер этот шаг не проходят.
 * Полная форма (с названием и ИНН) осталась для аккаунтов, заведённых
 * до этого порядка и пропустивших шаг, — у них компании ещё нет.
 */
class OnboardingController extends Controller
{
    public function company(Request $request): RedirectResponse|Response
    {
        if (! self::stepOpen($request)) {
            return redirect()->route('cabinet');
        }

        return Inertia::render('auth/CompanyStep', [
            'countries' => Country::listed()
                ->map(fn (Country $c): array => ['id' => $c->id, 'name' => $c->name()]),

            // Порядок внутри страны — по значимости города (sort):
            // в списке из трёх десятков российских городов Москва
            // должна стоять первой, а не там, куда её положил id
            'cities' => City::query()->where('is_active', true)->with('translations')->orderBy('sort')->orderBy('id')->get()
                ->map(fn (City $c): array => ['id' => $c->id, 'name' => $c->name(), 'country_id' => $c->country_id]),

            'categories' => Category::query()->whereNull('parent_id')->where('is_active', true)
                ->with('translations')->orderBy('sort')->orderBy('id')->get()
                ->map(fn (Category $c): array => ['id' => $c->id, 'slug' => $c->slug, 'name' => $c->name()]),

            'types' => Company::typeOptions(),

            // Физлицу и фрилансеру шаг показывает профиль человека:
            // без названия компании и типа бизнеса, имя — из регистрации
            'accountType' => self::accountType($request),
            'personName' => $request->user()->name,

            // Компания заведена при регистрации — спрашиваем только недостающее
            'completing' => $request->user()->company_id !== null,

            /*
             * Направления раздела «Услуги» — для блока, который
             * появляется при выборе типа компании «Услуги»: эйчар,
             * финансы и бухгалтерия, своё направление.
             */
            'serviceCategories' => Category::query()
                ->where('parent_id', Category::query()->where('slug', 'uslugi')->value('id'))
                ->where('is_active', true)
                ->with('translations')
                ->orderBy('sort')->orderBy('id')
                ->get()
                ->map(fn (Category $c): array => ['id' => $c->id, 'slug' => $c->slug, 'name' => $c->name()]),
        ]);
    }

    public function store(Request $request): RedirectResponse
    {
        if (! self::stepOpen($request)) {
            return redirect()->route('cabinet');
        }

        if ($request->user()->company !== null) {
            return $this->complete($request, $request->user()->company);
        }

        $form = self::accountType($request);
        $person = $form !== Company::LEGAL_ENTITY;

        $data = $request->validate([
            'name' => ['required', 'string', 'min:2', 'max:190'],
            // Тип бизнеса обязателен только компании: у физлица
            // и фрилансера его может просто не быть
            'type' => [$person ? 'nullable' : 'required', 'string', 'max:30'],
            'country_id' => ['required', 'exists:countries,id'],
            'city_id' => ['required', 'exists:cities,id'],
            'tin' => [
                'nullable', 'string', 'max:20',
                new Tin(Country::find($request->integer('country_id'))?->code, person: $person),
                Rule::unique('companies', 'tin')->whereNull('deleted_at'),
            ],
            'primary_role' => ['required', 'in:supplier,buyer,both'],
            'categories' => ['array', 'max:5'],
            'categories.*' => ['integer', 'exists:categories,id'],
            // Текст для «Другого»: чем занимается компания своими словами
            'custom_category' => ['nullable', 'string', 'max:80'],
        ], [
            'name.required' => __($person ? 'ui.messages.company.person_name_required' : 'ui.messages.company.name_required'),
            'type.required' => __('ui.messages.company.type_required'),
            'country_id.required' => __('ui.messages.company.country_required'),
            'city_id.required' => __('ui.messages.company.city_required'),
            'categories.max' => __('ui.messages.company.categories_max'),
            'tin.unique' => __('ui.messages.company.tin_unique'),
        ]);

        $company = Company::create([
            'name' => $data['name'],
            'type' => $data['type'] ?? null,
            'legal_form' => $form,
            'country_id' => $data['country_id'],
            'city_id' => $data['city_id'],
            'tin' => $data['tin'] ?? null,
            'primary_role' => $data['primary_role'],
            'custom_category' => $data['custom_category'] ?? null,
            'status' => Company::STATUS_ACTIVE,
        ]);

        $company->categories()->sync($data['categories'] ?? []);

        $request->user()->forceFill([
            'company_id' => $company->id,
            'company_role' => 'owner',
        ])->save();

        return redirect()->route('verification.notice')
            ->with('success', __('ui.messages.company.created_onboarding'));
    }

    /**
     * Дополнить компанию, заведённую при регистрации юрлица.
     *
     * Название, ИНН и категории уже указаны — здесь тип, страна, город
     * и роль. Направления услуг (при типе «Услуги») добавляются к уже
     * выбранным категориям, общий предел — пять.
     */
    private function complete(Request $request, Company $company): RedirectResponse
    {
        $data = $request->validate([
            'type' => ['required', 'string', 'max:30'],
            'country_id' => ['required', 'exists:countries,id'],
            'city_id' => ['required', 'exists:cities,id'],
            'primary_role' => ['required', 'in:supplier,buyer,both'],
            'categories' => ['array', 'max:5'],
            'categories.*' => ['integer', 'exists:categories,id'],
            'custom_category' => ['nullable', 'string', 'max:80'],
        ], [
            'type.required' => __('ui.messages.company.type_required'),
            'country_id.required' => __('ui.messages.company.country_required'),
            'city_id.required' => __('ui.messages.company.city_required'),
            'categories.max' => __('ui.messages.company.categories_max'),
        ]);

        $company->update([
            'type' => $data['type'],
            'country_id' => $data['country_id'],
            'city_id' => $data['city_id'],
            'primary_role' => $data['primary_role'],
            'custom_category' => $data['custom_category'] ?? $company->custom_category,
        ]);

        $categories = array_values(array_unique([
            ...$company->categories()->pluck('categories.id')->all(),
            ...array_map('intval', $data['categories'] ?? []),
        ]));
        $company->categories()->sync(array_slice($categories, 0, 5));

        return redirect()->route('verification.notice')
            ->with('success', __('ui.messages.company.created_onboarding'));
    }

    /**
     * Нужен ли шаг: компании ещё нет (старые аккаунты) или юрлицо
     * не дополнило заведённую при регистрации — у неё нет города.
     */
    private static function stepOpen(Request $request): bool
    {
        $company = $request->user()->company;

        return $company === null
            || ($company->legal_form === Company::LEGAL_ENTITY && $company->city_id === null);
    }

    /** Выбор с первого шага регистрации; неизвестное значение — юрлицо. */
    private static function accountType(Request $request): string
    {
        $type = (string) $request->user()->account_type;

        return in_array($type, Company::LEGAL_FORMS, true) ? $type : Company::LEGAL_ENTITY;
    }

    /** Пропустить шаг: аккаунт уже есть, и терять человека из-за формы нельзя. */
    public function skip(Request $request): RedirectResponse
    {
        return redirect()->route('verification.notice')
            ->with('warning', __('ui.messages.company.skipped'));
    }
}
