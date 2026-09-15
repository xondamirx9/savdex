<?php

declare(strict_types=1);

namespace App\Http\Requests\Auth;

use Illuminate\Foundation\Http\FormRequest;
use Illuminate\Validation\Rules\Password;
use Illuminate\Validation\Validator;

/**
 * Валидация регистрации.
 *
 * Сообщения не общие («поле некорректно»), а объясняющие, что именно не так
 * и как исправить, — правила 1 и 8 из §1 QA.md. Тексты совпадают с прототипом
 * (prototype/states.html, NEG-01).
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
        return [
            'name' => ['required', 'string', 'min:2', 'max:120'],
            'email' => ['required', 'string', 'email:rfc,strict', 'max:190', 'unique:users,email'],
            'phone' => ['required', 'string', 'regex:/^\+?\d[\d\s\-()]{8,17}$/'],
            'password' => [
                'required', 'string', 'confirmed',
                Password::defaults(),
            ],
            'terms' => ['accepted'],
            'locale' => ['nullable', 'string', 'in:ru,uz,en,zh,tr'],
        ];
    }

    /**
     * @return array<string, string>
     */
    public function messages(): array
    {
        return [
            'name.required' => __('ui.messages.register.name_required'),
            'name.min' => __('ui.messages.register.name_min'),

            'email.required' => __('ui.messages.register.email_required'),
            'email.email' => __('ui.messages.register.email_format'),
            'email.unique' => __('ui.messages.register.email_taken'),

            'phone.required' => __('ui.messages.register.phone_required'),
            'phone.regex' => __('ui.messages.phone_format'),

            'password.required' => __('ui.messages.auth.password_new'),
            'password.confirmed' => __('ui.messages.auth.password_mismatch'),
            'password.min' => __('ui.messages.register.password_min'),
            'password.letters' => __('ui.messages.register.password_letters'),
            'password.numbers' => __('ui.messages.register.password_numbers'),
            'password.uncompromised' => __('ui.messages.register.password_leaked'),

            'terms.accepted' => __('ui.messages.register.terms'),
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
        ]);
    }
}
