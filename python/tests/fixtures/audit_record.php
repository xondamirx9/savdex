<?php

/*
 * Строка журнала от PHP — для tests/test_audit_parity.py.
 *
 * Вход (stdin, JSON): номер автора, номер страны-предмета, действие,
 * раздел, изменения, примечание. Пишет через AdminLog::record — тем
 * путём, каким пишет вся админка Laravel.
 */

use App\Models\Country;
use App\Models\User;
use App\Support\AdminLog;
use Illuminate\Contracts\Console\Kernel;

$root = dirname(__DIR__, 3);

require $root.'/vendor/autoload.php';
$app = require $root.'/bootstrap/app.php';
$app->make(Kernel::class)->bootstrap();

$in = json_decode(stream_get_contents(STDIN), true);

AdminLog::record(
    $in['action'],
    $in['section'],
    $in['subject_id'] !== null ? Country::findOrFail($in['subject_id']) : null,
    $in['changes'] ?? [],
    $in['note'] ?? null,
    $in['actor_id'] !== null ? User::findOrFail($in['actor_id']) : null,
);
