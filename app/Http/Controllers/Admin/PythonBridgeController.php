<?php

declare(strict_types=1);

namespace App\Http\Controllers\Admin;

use App\Http\Controllers\Controller;
use App\Models\User;
use App\Support\PythonBridge;
use Illuminate\Http\Request;
use Illuminate\Http\Response;

/**
 * Переход из админки в раздел, который уже работает на Django.
 *
 * Стоит за входом в админку (authenticatedRoutes панели): сюда попадает
 * только вошедший сотрудник, сменивший выданный пароль. Отдаёт страницу,
 * которая сама отправляет пропуск в Django POST-запросом (PythonBridge).
 */
class PythonBridgeController extends Controller
{
    public function __invoke(Request $request): Response
    {
        $user = $request->user();
        abort_unless($user instanceof User, 403);

        return response()
            ->view('admin.python-bridge', [
                'action' => PythonBridge::LOGIN,
                'token' => PythonBridge::token($user, (string) $request->query('next', PythonBridge::HOME)),
            ])
            // Пропуск живёт минуту, но и минуту ему незачем лежать
            // в кэше или уходить в заголовке Referer
            ->header('Cache-Control', 'no-store')
            ->header('Referrer-Policy', 'no-referrer');
    }
}
