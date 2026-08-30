<?php

declare(strict_types=1);

namespace App\Http\Controllers\Cabinet;

use App\Http\Controllers\Controller;
use App\Models\City;
use App\Models\Company;
use App\Models\CompanyContact;
use App\Models\CompanyDocument;
use App\Models\Country;
use App\Rules\Tin;
use App\Support\ImageStore;
use Illuminate\Http\RedirectResponse;
use Illuminate\Http\Request;
use Illuminate\Validation\Rule;
use Inertia\Inertia;
use Inertia\Response;
use RuntimeException;

/**
 * Профиль компании: реквизиты, контакты, документы, сотрудники.
 *
 * Компания создаётся здесь же, если её ещё нет: отдельный экран
 * «сначала создайте компанию, потом заполните» — лишний шаг с теми же
 * полями.
 */
class CompanyProfileController extends Controller
{
    public function edit(Request $request): Response
    {
        $company = $request->user()->company;

        return Inertia::render('cabinet/Company', [
            'company' => $company === null ? null : [
                'id' => $company->id,
                'name' => $company->name,
                'slug' => $company->slug,
                'legal_name' => $company->legal_name,
                'tin' => $company->tin,
                'country_id' => $company->country_id,
                'city_id' => $company->city_id,
                'address' => $company->address,
                'description' => $company->description,
                'custom_category' => $company->custom_category,
                'website' => $company->website,
                'founded_year' => $company->founded_year,
                'employees_range' => $company->employees_range,
                'type' => $company->type,
                'primary_role' => $company->primary_role,
                'initials' => $company->initials(),
                'logo' => $company->logoUrl(),
                'cover' => $company->coverUrl(),
                'completeness' => $company->profileCompleteness(),
                'missing' => $company->missingProfileFields(),
                'verification_level' => $company->verification_level,
            ],

            'contacts' => $company?->contacts()->get()->map(fn (CompanyContact $c): array => [
                'id' => $c->id,
                'type' => $c->type,
                'value' => $c->value,
                'label' => $c->label,
                'contact_person' => $c->contact_person,
                'is_public' => $c->is_public,
            ]) ?? [],

            'documents' => $company?->documents()->latest()->get()->map(fn (CompanyDocument $d): array => [
                'id' => $d->id,
                'type' => $d->type,
                'type_label' => $d->typeLabel(),
                'title' => $d->title,
                'status' => $d->moderation_status,
                'size' => $d->sizeLabel(),
                'is_material' => $d->isMaterial(),
                'is_public' => $d->is_public,
                'valid_until' => $d->valid_until?->translatedFormat('d.m.Y'),
                'missing' => $d->fileMissing(),
            ]) ?? [],

            'employees' => $company?->users()->get()->map(fn ($u): array => [
                'id' => $u->id,
                'name' => $u->name,
                'email' => $u->email,
                'role' => $u->company_role === 'owner' ? 'Владелец' : 'Сотрудник',
                'verified' => $u->hasVerifiedEmail(),
            ]) ?? [],

            'countries' => Country::query()->where('is_active', true)->with('translations')->get()
                ->map(fn (Country $c): array => ['id' => $c->id, 'name' => $c->name()]),

            'cities' => City::query()->where('is_active', true)->with('translations')->get()
                ->map(fn (City $c): array => ['id' => $c->id, 'name' => $c->name(), 'country_id' => $c->country_id]),

            'verification' => $this->verificationChecklist($request, $company),

            'plan' => $company === null ? null : [
                'name' => $company->plan()->name,
                'verification_days' => $company->plan()->verification_days,
                'has_microsite' => (bool) $company->plan()->has_microsite,
            ],
        ]);
    }

    /**
     * Что уже подтверждено и что нужно для следующего уровня.
     *
     * @return list<array{label: string, done: bool, hint: string|null}>
     */
    private function verificationChecklist(Request $request, ?Company $company): array
    {
        $user = $request->user();

        return [
            ['label' => 'Почта подтверждена', 'done' => $user->hasVerifiedEmail(), 'hint' => null],
            ['label' => 'Телефон подтверждён кодом', 'done' => $user->phone_verified_at !== null, 'hint' => null],
            [
                'label' => 'Свидетельство о регистрации',
                'done' => (bool) $company?->documents()->where('type', 'registration')->where('moderation_status', 'approved')->exists(),
                'hint' => null,
            ],
            ['label' => 'ИНН/СТИР указан', 'done' => filled($company?->tin), 'hint' => null],
            [
                'label' => 'Лицензии и сертификаты',
                'done' => (bool) $company?->documents()->where('type', 'license')->where('moderation_status', 'approved')->exists(),
                'hint' => 'для уровня «Проверена+»',
            ],
            [
                'label' => 'Юридический адрес',
                'done' => filled($company?->address),
                'hint' => 'для уровня «Проверена+»',
            ],
        ];
    }

    public function update(Request $request): RedirectResponse
    {
        $data = $request->validate([
            'name' => ['required', 'string', 'min:2', 'max:190'],
            'legal_name' => ['nullable', 'string', 'max:255'],
            'tin' => [
                'nullable', 'string', 'max:20',
                new Tin(Country::find($request->integer('country_id'))?->code ?? $request->user()->company?->country?->code),
                Rule::unique('companies', 'tin')
                    ->ignore($request->user()->company_id)
                    ->whereNull('deleted_at'),
            ],
            'country_id' => ['nullable', 'exists:countries,id'],
            'city_id' => ['nullable', 'exists:cities,id'],
            'address' => ['nullable', 'string', 'max:255'],
            'description' => ['nullable', 'string', 'max:5000'],
            'website' => ['nullable', 'string', 'max:190'],
            'founded_year' => ['nullable', 'integer', 'between:1850,'.now()->year],
            'employees_range' => ['nullable', 'string', 'max:20'],
            'type' => ['nullable', 'string', 'max:30'],
            'custom_category' => ['nullable', 'string', 'max:80'],
            'primary_role' => ['nullable', 'in:supplier,buyer,both'],
        ], [
            'name.required' => 'Укажите название компании',
            'founded_year.between' => 'Год основания должен быть между 1850 и '.now()->year,
            'tin.unique' => 'Компания с таким ИНН уже зарегистрирована на площадке',
        ]);

        $user = $request->user();
        $company = $user->company;

        if ($company === null) {
            $company = Company::create([...$data, 'status' => 'active']);

            $user->forceFill(['company_id' => $company->id, 'company_role' => 'owner'])->save();

            return redirect()->route('cabinet.company')
                ->with('success', 'Компания создана. Теперь можно публиковать объявления.');
        }

        $company->fill($data)->save();

        return back()->with('success', 'Данные компании сохранены');
    }

    /**
     * Логотип компании.
     *
     * Отдельным запросом, а не полем общей формы: файл нельзя отправить
     * вместе с PATCH, а превращать сохранение профиля в multipart ради
     * одной необязательной картинки — плата за каждое сохранение.
     */
    public function uploadLogo(Request $request): RedirectResponse
    {
        $company = $request->user()->company;

        if ($company === null) {
            return back()->with('error', 'Сначала заполните данные компании');
        }

        $request->validate([
            'logo' => [
                'required', 'file',
                'mimes:'.implode(',', ImageStore::ALLOWED_MIMES),
                'max:'.ImageStore::MAX_SIZE_KB,
            ],
        ], [
            'logo.required' => 'Выберите файл',
            'logo.mimes' => 'Допустимы JPG, PNG и WebP',
            'logo.max' => 'Файл больше 8 МБ. Уменьшите разрешение или сожмите',
        ]);

        $store = app(ImageStore::class);

        try {
            $path = $store->store($request->file('logo'), "companies/{$company->id}", ImageStore::LOGO);
        } catch (RuntimeException) {
            return back()->with('error', 'Файл не удалось прочитать как изображение');
        }

        // Прежний удаляем после успешной записи нового: обратный
        // порядок оставил бы компанию без логотипа при сбое загрузки
        $previous = $company->logo_path;

        $company->forceFill(['logo_path' => $path])->save();

        $store->delete($previous);

        return back()->with('success', 'Логотип обновлён');
    }

    public function removeLogo(Request $request): RedirectResponse
    {
        $company = $request->user()->company;

        abort_if($company === null, 404);

        app(ImageStore::class)->delete($company->logo_path);

        $company->forceFill(['logo_path' => null])->save();

        return back()->with('success', 'Логотип удалён — на визитке снова инициалы');
    }

    /** Обложка визитки: фото вместо фирменного градиента в шапке. */
    public function uploadCover(Request $request): RedirectResponse
    {
        $company = $request->user()->company;

        if ($company === null) {
            return back()->with('error', 'Сначала заполните данные компании');
        }

        $request->validate([
            'cover' => [
                'required', 'file',
                'mimes:'.implode(',', ImageStore::ALLOWED_MIMES),
                'max:'.ImageStore::MAX_SIZE_KB,
            ],
        ], [
            'cover.required' => 'Выберите файл',
            'cover.mimes' => 'Допустимы JPG, PNG и WebP',
            'cover.max' => 'Файл больше 8 МБ. Уменьшите разрешение или сожмите',
        ]);

        $store = app(ImageStore::class);

        try {
            $path = $store->store($request->file('cover'), "companies/{$company->id}", ImageStore::COVER);
        } catch (RuntimeException) {
            return back()->with('error', 'Файл не удалось прочитать как изображение');
        }

        $previous = $company->cover_path;

        $company->forceFill(['cover_path' => $path])->save();

        $store->delete($previous);

        return back()->with('success', 'Обложка обновлена');
    }

    public function removeCover(Request $request): RedirectResponse
    {
        $company = $request->user()->company;

        abort_if($company === null, 404);

        app(ImageStore::class)->delete($company->cover_path);

        $company->forceFill(['cover_path' => null])->save();

        return back()->with('success', 'Обложка удалена — в шапке снова фирменный градиент');
    }
}
