<?php

declare(strict_types=1);

namespace App\Exceptions;

use RuntimeException;

/**
 * Не хватает средств на счету компании.
 *
 * Нужно, чтобы выйти из транзакции с откатом: возврат из замыкания
 * DB::transaction() её коммитит, а нехватка средств должна отменять
 * всё начатое.
 */
class InsufficientUnits extends RuntimeException {}
