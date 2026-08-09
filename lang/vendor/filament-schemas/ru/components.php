<?php

declare(strict_types=1);

/** Недостающие строки блоков схемы: врезки, секции, шаги мастера. */
return [
    'callout' => [
        'statuses' => [
            'danger' => 'Ошибка:',
            'info' => 'Обратите внимание:',
            'success' => 'Готово:',
            'warning' => 'Предупреждение:',
        ],
    ],

    'section' => [
        'actions' => [
            'collapse' => ['label' => 'Свернуть раздел'],
            'expand' => ['label' => 'Развернуть раздел'],
        ],
    ],

    'wizard' => [
        'header' => [
            'step' => [
                'statuses' => [
                    'completed' => 'Шаг пройден',
                    'upcoming' => 'Шаг не пройден',
                ],
            ],
        ],
    ],
];
