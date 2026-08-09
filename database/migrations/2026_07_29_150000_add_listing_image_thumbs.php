<?php

declare(strict_types=1);

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

/**
 * Уменьшенные копии фотографий объявлений.
 *
 * В каталоге двадцать карточек на страницу, и грузить в плитку
 * размером 400 пикселей файл на 1600 — это мегабайты трафика ради
 * изображения, которое всё равно ужмётся браузером. На мобильном
 * интернете, для которого площадка и делается, разница заметна.
 */
return new class extends Migration
{
    public function up(): void
    {
        Schema::table('listing_images', function (Blueprint $table): void {
            $table->string('thumb_path')->nullable()->after('path');
        });
    }

    public function down(): void
    {
        Schema::table('listing_images', function (Blueprint $table): void {
            $table->dropColumn('thumb_path');
        });
    }
};
