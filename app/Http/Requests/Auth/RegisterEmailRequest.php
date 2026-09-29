<?php

declare(strict_types=1);

namespace App\Http\Requests\Auth;

use Illuminate\Foundation\Http\FormRequest;
use Illuminate\Validation\Validator;

/**
 * Первый шаг регистрации — только почта.
 *
 * Правила и сообщения те же, что были у почты в общей форме
 * (RegisterRequest): занятый адрес отклоняется сразу, а не после
 * того, как человек ввёл код и заполнил всю анкету.
 */
class RegisterEmailRequest extends FormRequest
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
        return ['email' => RegisterRequest::emailRules()];
    }

    /**
     * @return array<string, string>
     */
    public function messages(): array
    {
        return RegisterRequest::emailMessages();
    }

    public function withValidator(Validator $validator): void
    {
        $validator->after(fn (Validator $v) => RegisterRequest::refineEmailError($v, (string) $this->input('email')));
    }

    protected function prepareForValidation(): void
    {
        $this->merge(['email' => mb_strtolower(trim((string) $this->input('email')))]);
    }
}
