<?php

declare(strict_types=1);

namespace Database\Seeders;

use App\Models\PromotionType;
use Illuminate\Database\Seeder;

/**
 * Инструменты продвижения — набор из раздела «Продвижение» прототипа.
 *
 * Прирост показов в effect_hint — ориентир, а не обещание: формулировка
 * «обычно» выбрана намеренно, гарантировать конкретную цифру площадка
 * не может и не должна.
 */
class PromotionTypeSeeder extends Seeder
{
    public function run(): void
    {
        $types = [
            [
                'code' => 'bump',
                'name' => 'Поднятие',
                'description' => 'Объявление возвращается в начало ленты по дате.',
                'effect_hint' => 'Обычно +40 % показов на 2 дня',
                'cost_units' => 1,
                'duration_days' => 2,
                'slots' => null,
                'badge' => null,
                'icon' => 'arrow-up',
                'sort' => 1,
            ],
            [
                'code' => 'category_top',
                'name' => 'ТОП категории',
                'description' => 'Первые три позиции в вашей категории.',
                'effect_hint' => 'Обычно +180 % показов',
                'cost_units' => 5,
                'duration_days' => 7,
                'slots' => 3,
                'badge' => 'ТОП',
                'icon' => 'star',
                'sort' => 2,
            ],
            [
                'code' => 'urgent',
                'name' => 'Срочно',
                'description' => 'Красный бейдж и повышение в ранжировании.',
                'effect_hint' => 'Обычно +75 % показов',
                'cost_units' => 3,
                'duration_days' => 7,
                'slots' => null,
                'badge' => 'Срочно',
                'icon' => 'clock',
                'sort' => 3,
            ],
            [
                'code' => 'highlight',
                'name' => 'Выделение',
                'description' => 'Цветная рамка карточки в списке.',
                'effect_hint' => 'Обычно +35 % переходов',
                'cost_units' => 2,
                'duration_days' => 14,
                'slots' => null,
                'badge' => null,
                'icon' => 'grid',
                'sort' => 4,
            ],
            [
                'code' => 'home_top',
                'name' => 'ТОП главной',
                'description' => 'Ротация в блоке на главной странице.',
                'effect_hint' => 'Обычно +320 % показов',
                'cost_units' => 12,
                'duration_days' => 7,
                'slots' => 6,
                'badge' => null,
                'icon' => 'home',
                'sort' => 5,
            ],
            [
                'code' => 'mailing',
                'name' => 'Рассылка по категории',
                'description' => 'Письмо подписчикам вашей категории.',
                'effect_hint' => 'Средняя открываемость 34 %',
                'cost_units' => 8,
                'duration_days' => 0,   // разовое
                'slots' => null,
                'badge' => null,
                'icon' => 'mail',
                'sort' => 6,
            ],
        ];

        foreach ($types as $type) {
            PromotionType::updateOrCreate(['code' => $type['code']], $type);
        }
    }
}
