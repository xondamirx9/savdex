<?php

/*
 * Права админки глазами PHP — для tests/test_access_parity.py.
 *
 * Python-разделы админки решают, что человеку можно, по своей копии
 * AdminAccess (python/savdex/access.py). Этот скрипт отвечает на те же
 * вопросы самим PHP: наборы прав ролей, «только свои записи» и итог
 * hasAdminAbility для сотрудников из stdin (роль, статус, выдачи и
 * отзывы поштучно). База не нужна: пользователь собирается в памяти.
 */

use App\Models\User;
use App\Support\AdminAccess;
use Illuminate\Contracts\Console\Kernel;

$root = dirname(__DIR__, 3);

require $root.'/vendor/autoload.php';
$app = require $root.'/bootstrap/app.php';
$app->make(Kernel::class)->bootstrap();

$cases = json_decode(stream_get_contents(STDIN), true) ?: [];
$roles = [...array_keys(AdminAccess::ROLES), 'unknown', null];

$out = [
    'all' => AdminAccess::all(),
    'roles' => [],
    'own' => [],
    'cases' => [],
];

foreach ($roles as $role) {
    $key = $role ?? '(null)';
    $out['roles'][$key] = AdminAccess::abilitiesFor($role);

    foreach (array_keys(AdminAccess::SECTIONS) as $section) {
        if (AdminAccess::scopeIsOwn($role, $section)) {
            $out['own'][$key][] = $section;
        }
    }
}

foreach ($cases as $case) {
    $user = (new User)->forceFill($case);
    $allowed = array_values(array_filter(AdminAccess::all(), fn (string $a): bool => $user->hasAdminAbility($a)));

    $out['cases'][] = [
        'allowed' => $allowed,
        'abilities' => $user->adminAbilities(),
        'superadmin' => $user->isSuperadmin(),
        'label' => $user->adminRoleLabel(),
        'own' => array_values(array_filter(array_keys(AdminAccess::SECTIONS), fn (string $s): bool => $user->adminScopeIsOwn($s))),
    ];
}

echo json_encode($out, JSON_UNESCAPED_UNICODE), "\n";
