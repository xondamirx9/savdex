<?php

declare(strict_types=1);

namespace App\Filament\Widgets;

use App\Support\PlatformMetrics;
use Filament\Widgets\Widget;

/**
 * Воронка активации: от регистрации до опубликованного объявления.
 *
 * Самый полезный график админки. Показывает не «сколько всего», а где
 * именно люди останавливаются — и потому прямо указывает, что чинить
 * следующим. Рядом с каждым шагом стоит здоровье площадки: показатели,
 * по которым проблему видно раньше, чем она дойдёт до выручки.
 */
class ActivationFunnel extends Widget
{
    protected string $view = 'filament.widgets.activation-funnel';

    protected static ?int $sort = 2;

    protected int|string|array $columnSpan = 'full';

    /** @return array<string, mixed> */
    protected function getViewData(): array
    {
        $metrics = new PlatformMetrics;

        return [
            'steps' => $metrics->activationFunnel(),
            'health' => $metrics->health(),
            'categories' => $metrics->topCategories(),
        ];
    }
}
