<?php

declare(strict_types=1);

namespace App\Http\Requests\Auth;

use App\Models\Company;
use App\Models\ItTask;
use App\Rules\Pinfl;
use App\Rules\Tin;
use App\Support\PasswordMessages;
use Illuminate\Foundation\Http\FormRequest;
use Illuminate\Validation\Rule;
use Illuminate\Validation\Rules\Password;
use Illuminate\Validation\Validator;

/**
 * Валидация регистрации.
 *
 * Сообщения не общие («поле некорректно»), а объясняющие, что именно не так
 * и как исправить, — правила 1 и 8 из §1 QA.md. Тексты совпадают с прототипом
 * (prototype/states.html, NEG-01).
 *
 * Набор полей зависит от того, кто регистрируется:
 * - юрлицо — название компании, ИНН (по желанию), Ф.И.О., категории каталога;
 * - физлицо — Ф.И.О. и ПИНФЛ (по желанию);
 * - фрилансер — Ф.И.О., ПИНФЛ и направление услуг, всё обязательно.
 * Почта, телефон и пароль нужны всем.
 */
class RegisterRequest extends FormRequest
{
    public function authorize(): bool
    {
        return true;
    }

    /**
     * @return array<string, mixed>
     */
    public function rules(): array
    {
        $type = $this->accountType();
        $legal = $type === Company::LEGAL_ENTITY;
        $freelancer = $type === Company::LEGAL_FREELANCER;

        return [
            'name' => ['required', 'string', 'min:2', 'max:120'],
            'email' => ['required', 'string', 'email:rfc,strict', 'max:190', 'unique:users,email'],
            'phone' => ['required', 'string', 'regex:/^\+?\d[\d\s\-()]{8,17}$/'],
            'password' => [
                'required', 'string', 'confirmed',
                Password::defaults(),
            ],
            'terms' => ['accepted'],
            'account_type' => ['nullable', 'in:legal,individual,freelancer'],
            'locale' => ['nullable', 'string', 'in:ru,uz,en,zh,tr'],

            // Юрлицо: компания заводится сразу, второй шаг только дополняет её
            'company_name' => $legal ? ['required', 'string', 'min:2', 'max:190'] : ['exclude'],
            'tin' => $legal
                ? ['nullable', 'string', 'max:20', new Tin('uz'), Rule::unique('companies', 'tin')->whereNull('deleted_at')]
                : ['exclude'],
            'categories' => $legal ? ['required', 'array', 'min:1', 'max:5'] : ['exclude'],
            'categories.*' => $legal
                ? ['integer', Rule::exists('categories', 'id')->whereNull('parent_id')->where('is_active', true)]
                : ['exclude'],

            // Физлицу ПИНФЛ по желанию, фрилансеру — обязательно
            'pinfl' => $legal
                ? ['exclude']
                : [$freelancer ? 'required' : 'nullable', 'string', new Pinfl, Rule::unique('companies', 'tin')->whereNull('deleted_at')],

            // Направление «Доп. услуг», на заказы которого фрилансер откликается
            'service_section' => $freelancer
                ? ['required', 'string', Rule::in(array_keys(ItTask::SERVICE_SECTIONS))]
                : ['exclude'],
        ];
    }

    /** Кто регистрируется; без выбора — юрлицо, как и по умолчанию в форме. */
    public function accountType(): string
    {
        $type = (string) $this->input('account_type');

        return in_array($type, Company::LEGAL_FORMS, true) ? $type : Company::LEGAL_ENTITY;
    }

    /**
     * @return array<string, string>
     */
    public function messages(): array
    {
        return [
            'name.required' => __('ui.messages.register.full_name_required'),
            'name.min' => __('ui.messages.register.name_min'),

            'email.required' => __('ui.messages.register.email_required'),
            'email.email' => __('ui.messages.register.email_format'),
            'email.unique' => __('ui.messages.register.email_taken'),

            'phone.required' => __('ui.messages.register.phone_required'),
            'phone.regex' => __('ui.messages.phone_format'),

            'password.required' => __('ui.messages.auth.password_new'),
            'password.confirmed' => __('ui.messages.auth.password_mismatch'),
            ...PasswordMessages::all(),

            'terms.accepted' => __('ui.messages.register.terms'),
            'account_type.in' => __('ui.messages.register.account_type'),

            'company_name.required' => __('ui.messages.company.name_required'),
            'company_name.min' => __('ui.messages.company.name_required'),
            'tin.unique' => __('ui.messages.company.tin_unique'),
            'categories.required' => __('ui.messages.register.categories_required'),
            'categories.min' => __('ui.messages.register.categories_required'),
            'categories.max' => __('ui.messages.company.categories_max'),
            'pinfl.required' => __('ui.messages.register.pinfl_required'),
            'pinfl.unique' => __('ui.messages.register.pinfl_unique'),
            'service_section.required' => __('ui.messages.register.service_section_required'),
            'service_section.in' => __('ui.messages.register.service_section_required'),
        ];
    }

    /**
     * Уточняем сообщение о почте: «нет собаки» и «адрес неполный» —
     * разные ошибки, и подсказка должна быть разной (NEG-06b).
     */
    public function withValidator(Validator $validator): void
    {
        /*
         * Правило confirmed вешает ошибку на password, и подпись
         * «Пароли не совпадают» появлялась под первым полем — хотя ошибся
         * человек во втором. Дублируем сообщение туда, где его ждут.
         */
        $validator->after(function (Validator $v): void {
            // По правилу, а не по тексту: текст приходит из словаря
            // и на другом языке сравнение со строкой перестало бы работать
            if (array_key_exists('Confirmed', $v->failed()['password'] ?? [])) {
                $v->errors()->add('password_confirmation', __('ui.messages.auth.password_mismatch'));
            }
        });

        $validator->after(function (Validator $v): void {
            $email = (string) $this->input('email');

            if ($email === '' || ! $v->errors()->has('email')) {
                return;
            }

            // Сообщение об уже занятом адресе перекрывать не нужно — оно полезнее.
            // Смотрим на сработавшее правило, а не на текст: текст переводится
            if (array_key_exists('Unique', $v->failed()['email'] ?? [])) {
                return;
            }

            $message = ! str_contains($email, '@')
                ? __('ui.messages.register.email_no_at')
                : (! str_contains(substr($email, (int) strpos($email, '@')), '.')
                    ? __('ui.messages.register.email_incomplete')
                    : null);

            if ($message !== null) {
                $v->errors()->forget('email');
                $v->errors()->add('email', $message);
            }
        });
    }

    protected function prepareForValidation(): void
    {
        $this->merge([
            'email' => mb_strtolower(trim((string) $this->input('email'))),
            'name' => trim((string) $this->input('name')),
            'company_name' => trim((string) $this->input('company_name')),
            // Пробелы и дефисы из вставленного номера — не ошибка человека
            'tin' => preg_replace('/[\s\-]+/', '', (string) $this->input('tin')) ?: null,
            'pinfl' => preg_replace('/[\s\-]+/', '', (string) $this->input('pinfl')) ?: null,
        ]);
    }
}
