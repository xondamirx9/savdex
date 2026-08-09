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
            'name.required' => 'Как к вам обращаться? Укажите имя',
            'name.min' => 'Имя слишком короткое',

            'email.required' => 'Введите рабочую почту',
            'email.email' => 'Проверьте адрес: нужен формат name@company.uz',
            'email.unique' => 'На этот адрес уже зарегистрирована компания. Войдите или восстановите пароль',

            'phone.required' => 'Введите номер телефона',
            'phone.regex' => 'Номер должен содержать от 9 до 15 цифр. Например: +998 90 123-45-67',

            'password.required' => 'Придумайте пароль',
            'password.confirmed' => 'Пароли не совпадают',
            'password.min' => 'Пароль должен быть не короче 10 символов',
            'password.letters' => 'Добавьте в пароль хотя бы одну букву',
            'password.numbers' => 'Добавьте в пароль хотя бы одну цифру',
            'password.uncompromised' => 'Этот пароль встречается в утечках данных. Придумайте другой',

            'terms.accepted' => 'Нужно принять оферту и политику конфиденциальности',
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
            if ($v->errors()->first('password') === 'Пароли не совпадают') {
                $v->errors()->add('password_confirmation', 'Пароли не совпадают');
            }
        });

        $validator->after(function (Validator $v): void {
            $email = (string) $this->input('email');

            if ($email === '' || ! $v->errors()->has('email')) {
                return;
            }

            // Сообщение об уже занятом адресе перекрывать не нужно — оно полезнее
            if (str_contains((string) $v->errors()->first('email'), 'уже зарегистрирована')) {
                return;
            }

            $message = ! str_contains($email, '@')
                ? 'В адресе не хватает знака @. Например: rustam@company.uz'
                : (! str_contains(substr($email, (int) strpos($email, '@')), '.')
                    ? 'Похоже, адрес неполный. Нужен формат name@company.uz'
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
