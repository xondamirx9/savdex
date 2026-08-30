<?php

declare(strict_types=1);

use App\Support\SearchText;
use Illuminate\Database\Migrations\Migration;
use Illuminate\Support\Facades\DB;

/**
 * Пересборка search_text: текст в обеих графиках.
 *
 * Модель теперь пишет в search_text кириллицу и латиницу разом
 * (SearchText::index), но существующие объявления проиндексированы
 * по-старому — «sement» так и находил бы ноль. Здесь их индекс
 * пересобирается по тому же правилу, что в модели.
 */
return new class extends Migration
{
    public function up(): void
    {
        DB::table('listings')
            ->select('id', 'title', 'description')
            ->orderBy('id')
            ->chunkById(200, function ($rows): void {
                foreach ($rows as $row) {
                    DB::table('listings')->where('id', $row->id)->update([
                        'search_text' => SearchText::index($row->title.' '.$row->description),
                    ]);
                }
            });
    }

    public function down(): void
    {
        // Прежний индекс — подмножество нового; откатывать нечего.
    }
};
