<?php

declare(strict_types=1);

namespace App\Rules;

use Closure;
use Illuminate\Contracts\Validation\ValidationRule;

/**
 * ПИНФЛ — персональный идентификационный номер физлица в Узбекистане.
 *
 * Ровно 14 цифр. Повтор одной цифры («11111111111111») — не номер,
 * а способ пройти обязательное поле, поэтому отклоняется.
 */
class Pinfl implements ValidationRule
{
    public function validate(string $attribute, mixed $value, Closure $fail): void
    {
        $pinfl = (string) $value;

        if (preg_match('/^\d{14}$/', $pinfl) !== 1) {
            $fail(__('ui.messages.register.pinfl_format'));

            return;
        }

        if (preg_match('/^(\d)\1+$/', $pinfl) === 1) {
            $fail(__('ui.messages.register.pinfl_invalid'));
        }
    }
}
