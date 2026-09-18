<?php

declare(strict_types=1);

namespace App\Http\Controllers\Cabinet;

use App\Http\Controllers\Controller;
use App\Services\Messaging\TelegramGateway;
use Illuminate\Http\RedirectResponse;
use Illuminate\Http\Request;
use Inertia\Inertia;
use Symfony\Component\HttpFoundation\Response;

/**
 * Привязка Telegram из кабинета.
 *
 * Ссылку на бот выдаёт сервер, а не собирает страница: в ней
 * одноразовый токен, который нельзя показывать заранее — он живёт
 * пятнадцать минут с момента нажатия.
 */
class TelegramLinkController extends Controller
{
    public function store(Request $request, TelegramGateway $telegram): Response
    {
        if (! $telegram->configured()) {
            return back()->withErrors(['telegram' => __('ui.messages.auth.telegram_unavailable')]);
        }

        /*
         * Уходим к боту: чат придёт вебхуком, пока человек жмёт там
         * «Старт». Inertia::location, а не обычный редирект: страница
         * живёт в Inertia, и чужой домен она сама открыть не может —
         * ответ с этим заголовком велит браузеру перейти целиком.
         */
        return Inertia::location($telegram->linkUrl($request->user()));
    }

    public function destroy(Request $request): RedirectResponse
    {
        $request->user()->forceFill([
            'telegram_chat_id' => null,
            'telegram_username' => null,
            'telegram_linked_at' => null,
        ])->save();

        return back()->with('status', __('ui.messages.auth.telegram_unlinked'));
    }
}
