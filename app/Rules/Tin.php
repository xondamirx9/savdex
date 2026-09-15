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
            $fail(__('ui.messages.tin.digits_only'));

            return;
        }

        // Повторы одной цифры и учебные последовательности
        if (preg_match('/^(\d)\1+$/', $tin) === 1 || in_array($tin, self::FAKE, true)) {
            $fail(__('ui.messages.tin.invalid'));

            return;
        }

        if ($this->countryCode === null || $this->countryCode === 'uz') {
            if (strlen($tin) !== 9) {
                $fail(__('ui.messages.tin.uz_length'));
            }

            return;
        }

        if (strlen($tin) < 6 || strlen($tin) > 15) {
            $fail(__('ui.messages.tin.length'));
        }
    }
}
