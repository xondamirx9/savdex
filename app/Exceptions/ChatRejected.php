<?php

declare(strict_types=1);

namespace App\Exceptions;

use RuntimeException;

/**
 * Отклик или сообщение не приняты: лимит тарифа, своё объявление,
 * чужой тред. Сообщение исключения показывается человеку как есть —
 * оно объясняет причину отказа, как и в PromoCodeRejected.
 */
class ChatRejected extends RuntimeException {}
