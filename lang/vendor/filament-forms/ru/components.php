<?php

declare(strict_types=1);

/**
 * Недостающие строки полей формы Filament.
 *
 * Часть из них видна прямо на экране: заголовки столбцов в повторителях,
 * кнопки у загруженных файлов, подписи в выборе даты. Остальные читает
 * экранный диктор — и без перевода он произносит английский ключ
 * посреди русской формы.
 */
return [
    'color_picker' => [
        'panel_label' => 'Выбор цвета',
    ],

    'date_time_picker' => [
        'month_select' => ['label' => 'Месяц'],
        'year_input' => ['label' => 'Год'],
        'hour_input' => ['label' => 'Часы'],
        'minute_input' => ['label' => 'Минуты'],
        'second_input' => ['label' => 'Секунды'],
    ],

    'file_upload' => [
        'actions' => [
            'download' => ['label' => 'Скачать'],
            'open' => ['label' => 'Открыть в новой вкладке'],
        ],
        'editor' => ['label' => 'Редактор изображения'],
    ],

    'key_value' => [
        'columns' => [
            'actions' => ['label' => 'Действия'],
            'reorder' => ['label' => 'Переставить'],
        ],
    ],

    'repeater' => [
        'columns' => [
            'actions' => ['label' => 'Действия'],
            'reorder' => ['label' => 'Переставить'],
        ],
    ],

    'rich_editor' => [
        'toolbar' => ['label' => 'Панель редактора'],
    ],

    'tags_input' => [
        'tag_added' => 'Добавлено: :tag',
        'tag_removed' => 'Удалено: :tag',
    ],
];
