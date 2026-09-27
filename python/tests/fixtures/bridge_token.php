<?php

/*
 * Пропуск в Django от настоящего Laravel — для tests/test_bridge_parity.py.
 *
 * Аргументы: номер пользователя, адрес, сдвиг времени в секундах
 * (отрицательный — пропуск, выданный в прошлом). Печатает пропуск.
 */

use App\Models\User;
use App\Support\PythonBridge;
use Illuminate\Contracts\Console\Kernel;

$root = dirname(__DIR__, 3);

require $root.'/vendor/autoload.php';
$app = require $root.'/bootstrap/app.php';
$app->make(Kernel::class)->bootstrap();

[, $uid, $next, $shift] = $argv + [3 => '0'];

$user = (new User)->forceFill(['id' => (int) $uid]);

echo PythonBridge::token($user, $next, time() + (int) $shift), "\n";
