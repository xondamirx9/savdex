<?php

declare(strict_types=1);

namespace Tests\Support;

use App\Models\Category;

/**
 * Поля компании для регистрации юрлица.
 *
 * С первого шага юрлицо указывает название компании и хотя бы одну
 * категорию каталога — без них форма не проходит.
 */
trait LegalRegistration
{
    /** @return array{company_name: string, categories: list<int>} */
    protected function legalFields(): array
    {
        $category = Category::query()->whereNull('parent_id')->where('is_active', true)->first()
            ?? Category::factory()->create();

        return [
            'company_name' => 'ООО «Стройбаза»',
            'categories' => [$category->id],
        ];
    }
}
