<?php

declare(strict_types=1);

namespace App\Console\Commands;

use App\Models\User;
use App\Support\AdminAccess;
use Illuminate\Console\Command;
use Illuminate\Support\Str;

/**
 * Выдать доступ в админку.
 *
 * До этой команды администратор заводился только правкой базы: сидера
 * для него нет намеренно — учётка с известным паролем, приехавшая
 * на прод вместе с демо-данными, это открытая дверь.
 *
 * Пароль показывается один раз и требует смены при первом входе:
 * выданный вручную пароль знают двое, и до замены доступ нельзя
 * считать принадлежащим человеку.
 */
class MakeAdmin extends Command
{
    protected $signature = 'savdex:admin
        {email : Почта администратора}
        {--name= : Имя, если пользователя ещё нет}
        {--moderator : Выдать роль модератора вместо суперадмина}
        {--role= : Любая из ролей: admin, sales, supplier_manager, buyer_manager, moderator, finance, support, content_manager, superadmin}
        {--password= : Свой пароль вместо сгенерированного}';

    protected $description = 'Создать администратора или выдать роль существующему пользователю';

    public function handle(): int
    {
        $email = mb_strtolower(trim((string) $this->argument('email')));

        if (! filter_var($email, FILTER_VALIDATE_EMAIL)) {
            $this->error("«{$email}» не похоже на адрес почты.");

            return self::FAILURE;
        }

        $role = $this->chooseRole();

        if ($role === null) {
            return self::FAILURE;
        }

        $user = User::where('email', $email)->first();
        $password = (string) ($this->option('password') ?: Str::password(14, symbols: false));

        if ($user === null) {
            $user = new User(['name' => (string) ($this->option('name') ?: Str::before($email, '@'))]);
            $user->email = $email;
            $created = true;
        } else {
            $created = false;
        }

        $user->forceFill([
            'is_admin' => true,
            'admin_role' => $role,
            'status' => 'active',
            'password' => $password,
            'must_change_password' => true,
            // Администратор без подтверждённой почты не пройдёт
            // собственные же проверки площадки
            'email_verified_at' => $user->email_verified_at ?? now(),
        ])->save();

        $this->newLine();
        $this->info($created ? 'Администратор создан.' : 'Роль выдана существующему пользователю, пароль заменён.');

        $this->table(['Поле', 'Значение'], [
            ['Адрес', url('/admin')],
            ['Почта', $email],
            ['Пароль', $password],
            ['Роль', $user->adminRoleLabel()],
        ]);

        $this->warn('Пароль показан один раз. При первом входе система попросит его сменить.');

        return self::SUCCESS;
    }

    /**
     * Какую роль выдать.
     *
     * Флаг --moderator оставлен ради тех, у кого он записан в заметках,
     * но теперь ролей девять, и общий --role точнее. Неизвестное имя —
     * отказ со списком: молча выдать «никаких прав» хуже, чем не выдать
     * ничего, потому что человек уйдёт с пустой панелью и без подсказки.
     */
    private function chooseRole(): ?string
    {
        $role = (string) ($this->option('role') ?: '');

        if ($role === '') {
            return $this->option('moderator') ? User::ADMIN_MODERATOR : User::ADMIN_SUPERADMIN;
        }

        if (! AdminAccess::isRole($role)) {
            $this->error("Роли «{$role}» нет. Доступны: ".implode(', ', array_keys(AdminAccess::ROLES)).'.');

            return null;
        }

        return $role;
    }
}
