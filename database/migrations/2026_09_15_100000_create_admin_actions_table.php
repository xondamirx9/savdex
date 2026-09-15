<?php

declare(strict_types=1);

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

/**
 * Журнал действий администраторов.
 *
 * Без него девять ролей не имеют смысла: разграничение, которое нельзя
 * проверить постфактум, — это договорённость, а не защита.
 *
 * Имя автора и название записи хранятся снимком, а не только ссылкой.
 * Ссылка умирает вместе с удалённым пользователем, и запись «кто-то
 * заблокировал кого-то» отвечает ровно на те вопросы, ради которых
 * журнал не заводят.
 *
 * Колонки updated_at нет намеренно: записи журнала не меняются. Модель
 * запрещает правку и удаление отдельно, но и в схеме этого места быть
 * не должно.
 */
return new class extends Migration
{
    public function up(): void
    {
        Schema::create('admin_actions', function (Blueprint $table): void {
            $table->id();

            /*
             * Ссылка на автора — без внешнего ключа.
             *
             * Журнал обязан пережить всё, что описывает, включая удаление
             * самого автора. С внешним ключом запись об удалении сотрудника
             * не вставлялась вовсе: она ссылается на строку, которой в этот
             * момент уже нет. Отвечает на вопрос «кто» снимок имени ниже,
             * а ссылка нужна лишь для удобной связи, пока автор существует.
             */
            $table->unsignedBigInteger('user_id')->nullable();
            $table->string('user_name', 120);
            $table->string('user_role', 20)->nullable();

            // «approved», «blocked», «granted» — что именно сделали
            $table->string('action', 40);
            // Раздел прав из AdminAccess: по нему журнал фильтруется
            $table->string('section', 40);

            $table->nullableMorphs('subject');
            $table->string('subject_label', 200)->nullable();

            // {"before": {...}, "after": {...}}
            $table->json('changes')->nullable();
            $table->text('note')->nullable();
            $table->string('ip', 45)->nullable();

            $table->timestamp('created_at')->index();

            $table->index(['section', 'created_at']);
            $table->index(['user_id', 'created_at']);
        });
    }

    public function down(): void
    {
        Schema::dropIfExists('admin_actions');
    }
};
