<?php

declare(strict_types=1);

namespace App\Rules;

use Closure;
use Illuminate\Contracts\Validation\ValidationRule;

/**
 * ИНН (СТИР) компании.
 *
 * В Узбекистане это ровно девять цифр — «2345678» и «123456789»
 * в боевом каталоге подрывают доверие сильнее пустого поля (аудит
 * 29.08.2026, п. 3.2). Для иностранных компаний формат свой,
 * поэтому жёсткая девятка применяется только к Узбекистану.
 */
class Tin implements ValidationRule
{
    /** Очевидно ненастоящие последовательности. */
    private const FAKE = ['123456789', '987654321', '123123123'];

    public function __construct(private readonly ?string $countryCode = null) {}

    public function validate(string $attribute, mixed $value, Closure $fail): void
    {
        $tin = (string) $value;

        if (preg_match('/^\d+$/', $tin) !== 1) {
            $fail('ИНН состоит только из цифр.');

            return;
        }

        // Повторы одной цифры и учебные последовательности
        if (preg_match('/^(\d)\1+$/', $tin) === 1 || in_array($tin, self::FAKE, true)) {
            $fail('Указан недействительный ИНН.');

            return;
        }

        if ($this->countryCode === null || $this->countryCode === 'uz') {
            if (strlen($tin) !== 9) {
                $fail('ИНН (СТИР) в Узбекистане — ровно 9 цифр.');
            }

            return;
        }

        if (strlen($tin) < 6 || strlen($tin) > 15) {
            $fail('ИНН должен содержать от 6 до 15 цифр.');
        }
    }
}
