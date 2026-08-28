<?php

declare(strict_types=1);

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

/**
 * MIME-тип не помещался в varchar(64): у файлов Office он длиннее —
 * «application/vnd.openxmlformats-officedocument.presentationml.
 * presentation» занимает 73 символа. Postgres обрезать молча
 * отказывается, и загрузка презентации падала ошибкой 500;
 * PDF и картинки с короткими типами проходили.
 */
return new class extends Migration
{
    public function up(): void
    {
        Schema::table('company_documents', function (Blueprint $table): void {
            $table->string('mime', 255)->nullable()->change();
        });
    }

    public function down(): void
    {
        Schema::table('company_documents', function (Blueprint $table): void {
            $table->string('mime', 64)->nullable()->change();
        });
    }
};
