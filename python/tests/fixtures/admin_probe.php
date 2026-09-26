<?php

/*
 * Что Laravel думает о пользователе — для tests/test_admin_parity.py.
 *
 * Сверка строк в базе не отвечает на главный вопрос: войдёт ли
 * администратор, заведённый Python-версией, в админку Laravel. Этот
 * скрипт спрашивает у самого Laravel: принимает ли его проверка пароля
 * (Hash::check с проверкой алгоритма, как при входе), пускает ли
 * панель и какой видится роль.
 *
 * Вход: почта и пароль аргументами. Выход: одна строка JSON.
 */

use App\Models\User;
use Filament\Facades\Filament;
use Illuminate\Contracts\Console\Kernel;
use Illuminate\Support\Facades\Hash;

$root = dirname(__DIR__, 3);

require $root.'/vendor/autoload.php';
$app = require $root.'/bootstrap/app.php';
$app->make(Kernel::class)->bootstrap();

[, $email, $password] = $argv;

$user = User::where('email', $email)->firstOrFail();

try {
    $check = Hash::check($password, $user->password);
} catch (Throwable $e) {
    $check = 'исключение: '.$e->getMessage();
}

echo json_encode([
    'password_ok' => $check,
    'panel' => $user->canAccessPanel(Filament::getPanel('admin')),
    'role_label' => $user->adminRoleLabel(),
    'must_change_password' => $user->must_change_password,
    'verified' => $user->email_verified_at !== null,
], JSON_UNESCAPED_UNICODE), "\n";
