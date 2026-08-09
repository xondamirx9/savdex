<?php

declare(strict_types=1);

namespace App\Http\Controllers;

use App\Models\UserNotification;
use Illuminate\Http\RedirectResponse;
use Illuminate\Http\Request;
use Inertia\Inertia;
use Inertia\Response;

/**
 * Уведомления пользователя.
 *
 * Колокольчик в шапке показывает последние пять и число непрочитанных,
 * полный список — на отдельной странице: выпадающий блок на сорок
 * записей превращается в собственную страницу внутри шапки.
 */
class NotificationController extends Controller
{
    public function index(Request $request): Response
    {
        $filter = $request->string('filter')->toString();

        $notifications = $request->user()->alerts()
            ->when($filter === 'unread', fn ($q) => $q->whereNull('read_at'))
            ->latest()
            ->limit(100)
            ->get()
            ->map($this->present(...));

        return Inertia::render('Notifications', [
            'notifications' => $notifications,
            'filter' => $filter === 'unread' ? 'unread' : 'all',
            'unread' => $request->user()->alerts()->unread()->count(),
        ]);
    }

    /** @return array<string, mixed> */
    private function present(UserNotification $n): array
    {
        return [
            'id' => $n->id,
            'type' => $n->type,
            'tone' => $n->tone,
            'title' => $n->title,
            'body' => $n->body,
            'url' => $n->url,
            'is_broadcast' => $n->is_broadcast,
            'read' => $n->read_at !== null,
            'ago' => $n->created_at->diffForHumans(),
            'date' => $n->created_at->translatedFormat('d.m.Y в H:i'),
        ];
    }

    public function read(Request $request, int $id): RedirectResponse
    {
        $notification = $request->user()->alerts()->find($id);

        abort_if($notification === null, 404);

        $notification->markRead();

        /*
         * Уведомление почти всегда ведёт куда-то: открыть его и остаться
         * на месте — лишний шаг.
         *
         * Уводим только внутрь площадки. Сейчас адрес заполняет наш же
         * код и рассылки суперадмина, но redirect() на непроверенный
         * абсолютный адрес — это открытый редирект, и он переживёт того,
         * кто помнит про это ограничение.
         */
        $url = $notification->url;

        return $url !== null && str_starts_with($url, '/')
            ? redirect($url)
            : back();
    }

    public function readAll(Request $request): RedirectResponse
    {
        $request->user()->alerts()->unread()->update(['read_at' => now()]);

        return back()->with('success', 'Все уведомления отмечены прочитанными');
    }
}
