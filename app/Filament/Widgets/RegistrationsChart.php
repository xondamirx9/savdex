<?php

declare(strict_types=1);

namespace App\Filament\Widgets;

use App\Support\PlatformMetrics;
use Filament\Widgets\ChartWidget;

/**
 * Регистрации по дням.
 *
 * Две линии вместо одной: разрыв между пользователями и компаниями
 * показывает, сколько людей застревают на втором шаге регистрации.
 * Одна общая линия этого не покажет.
 */
class RegistrationsChart extends ChartWidget
{
    protected ?string $heading = 'Регистрации по дням';

    protected ?string $description = 'Разрыв между линиями — люди, не дошедшие до создания компании';

    protected static ?int $sort = 3;

    protected int|string|array $columnSpan = 'full';

    protected function getData(): array
    {
        $data = (new PlatformMetrics)->registrationsByDay();

        return [
            'datasets' => [
                [
                    'label' => 'Пользователи',
                    'data' => $data['users'],
                    'borderColor' => '#1d4ed8',
                    'backgroundColor' => 'rgba(29, 78, 216, 0.08)',
                    'fill' => true,
                    'tension' => 0.3,
                ],
                [
                    'label' => 'Компании',
                    'data' => $data['companies'],
                    'borderColor' => '#0f766e',
                    'backgroundColor' => 'rgba(15, 118, 110, 0.08)',
                    'fill' => true,
                    'tension' => 0.3,
                ],
            ],
            'labels' => $data['labels'],
        ];
    }

    protected function getType(): string
    {
        return 'line';
    }

    /**
     * Целые числа на оси: регистраций не бывает 2,5 — дробные деления
     * на малых объёмах выглядят как ошибка данных.
     */
    protected function getOptions(): array
    {
        return [
            'scales' => [
                'y' => [
                    'beginAtZero' => true,
                    'ticks' => ['precision' => 0],
                ],
            ],
        ];
    }
}
