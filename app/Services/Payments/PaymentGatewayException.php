<?php

declare(strict_types=1);

namespace App\Services\Payments;

use RuntimeException;

/**
 * Ошибка платёжного шлюза: провайдер выключен, не настроен или
 * вернул отказ. Отдельный тип, чтобы обработчик колбэков и кнопка
 * оплаты отличали «провайдер сломался» от прочих ошибок.
 */
class PaymentGatewayException extends RuntimeException {}
