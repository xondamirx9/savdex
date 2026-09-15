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
 */
class OnboardingController extends Controller
{
    public function company(Request $request): RedirectResponse|Response
    {
        // Компания уже есть — шаг пройден, повторять его незачем
        if ($request->user()->company_id !== null) {
            return redirect()->route('cabinet');
        }

        return Inertia::render('auth/CompanyStep', [
            'countries' => Country::query()->where('is_active', true)->with('translations')->orderBy('sort')->get()
                ->map(fn (Country $c): array => ['id' => $c->id, 'name' => $c->name()]),

            'cities' => City::query()->where('is_active', true)->with('translations')->get()
                ->map(fn (City $c): array => ['id' => $c->id, 'name' => $c->name(), 'country_id' => $c->country_id]),

            'categories' => Category::query()->whereNull('parent_id')->where('is_active', true)
                ->with('translations')->orderBy('sort')->get()
                ->map(fn (Category $c): array => ['id' => $c->id, 'slug' => $c->slug, 'name' => $c->name()]),

            'types' => Company::typeOptions(),

            /*
             * Направления раздела «Услуги» — для блока, который
             * появляется при выборе типа компании «Услуги»: эйчар,
             * финансы и бухгалтерия, своё направление.
             */
            'serviceCategories' => Category::query()
                ->where('parent_id', Category::query()->where('slug', 'uslugi')->value('id'))
                ->where('is_active', true)
                ->with('translations')
                ->orderBy('sort')
                ->get()
                ->map(fn (Category $c): array => ['id' => $c->id, 'slug' => $c->slug, 'name' => $c->name()]),
        ]);
    }

    public function store(Request $request): RedirectResponse
    {
        if ($request->user()->company_id !== null) {
            return redirect()->route('cabinet');
        }

        $data = $request->validate([
            'name' => ['required', 'string', 'min:2', 'max:190'],
            'type' => ['required', 'string', 'max:30'],
            'country_id' => ['required', 'exists:countries,id'],
            'city_id' => ['required', 'exists:cities,id'],
            'tin' => [
                'nullable', 'string', 'max:20',
                new Tin(Country::find($request->integer('country_id'))?->code),
                Rule::unique('companies', 'tin')->whereNull('deleted_at'),
            ],
            'primary_role' => ['required', 'in:supplier,buyer,both'],
            'categories' => ['array', 'max:5'],
            'categories.*' => ['integer', 'exists:categories,id'],
            // Текст для «Другого»: чем занимается компания своими словами
            'custom_category' => ['nullable', 'string', 'max:80'],
        ], [
            'name.required' => __('ui.messages.company.name_required'),
            'type.required' => __('ui.messages.company.type_required'),
            'country_id.required' => __('ui.messages.company.country_required'),
            'city_id.required' => __('ui.messages.company.city_required'),
            'categories.max' => __('ui.messages.company.categories_max'),
            'tin.unique' => __('ui.messages.company.tin_unique'),
        ]);

        $company = Company::create([
            'name' => $data['name'],
            'type' => $data['type'],
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

    /** Пропустить шаг: аккаунт уже есть, и терять человека из-за формы нельзя. */
    public function skip(Request $request): RedirectResponse
    {
        return redirect()->route('verification.notice')
            ->with('warning', __('ui.messages.company.skipped'));
    }
}
