<?php

declare(strict_types=1);

namespace App\Http\Controllers\Cabinet;

use App\Exceptions\ChatRejected;
use App\Http\Controllers\Controller;
use App\Models\Listing;
use App\Models\Message;
use App\Models\MessageThread;
use App\Services\ChatService;
use Illuminate\Http\RedirectResponse;
use Illuminate\Http\Request;
use Illuminate\Support\Str;
use Inertia\Inertia;
use Inertia\Response;

/**
 * Чаты кабинета: отклики на объявления и переписка между компаниями.
 *
 * Обновление без вебсокетов: страница разговора перезапрашивает
 * сообщения раз в несколько секунд частичной перезагрузкой Inertia.
 * На бесплатном хостинге это честнее постоянного соединения, а для
 * B2B-переписки задержка в десять секунд не задержка.
 */
class ChatController extends Controller
{
    public function __construct(private readonly ChatService $chat) {}

    /** Список разговоров компании — покупательских и продавецких вперемешку. */
    public function index(Request $request): Response
    {
        $company = $request->user()->company;

        if ($company === null) {
            return Inertia::render('cabinet/Chats', ['threads' => [], 'hasCompany' => false]);
        }

        $threads = MessageThread::query()
            ->participant($company)
            ->with(['listing', 'buyer', 'seller'])
            ->orderByDesc('last_message_at')
            ->limit(100)
            ->get();

        // Последние реплики и непрочитанное — двумя запросами на список,
        // а не парой запросов на каждый тред
        $lastMessages = Message::query()
            ->whereIn('id', Message::query()
                ->selectRaw('max(id)')
                ->whereIn('thread_id', $threads->pluck('id'))
                ->groupBy('thread_id'))
            ->get()
            ->keyBy('thread_id');

        return Inertia::render('cabinet/Chats', [
            'hasCompany' => true,
            'threads' => $threads->map(function (MessageThread $t) use ($company, $lastMessages): array {
                $other = $t->counterpart($company);
                $last = $lastMessages->get($t->id);

                return [
                    'id' => $t->id,
                    'company' => $other?->name ?? 'Компания удалена',
                    'initials' => $other?->initials() ?? '—',
                    'listing' => $t->listing?->title,
                    'last' => $last === null ? null : Str::limit($last->body, 80),
                    'last_mine' => $last !== null && $last->company_id === $company->id,
                    'at' => $t->last_message_at?->diffForHumans(),
                    'unread' => $t->unreadCountFor($company),
                ];
            }),
        ]);
    }

    public function show(Request $request, int $id): Response
    {
        $company = $request->user()->company;
        abort_if($company === null, 404);

        $thread = MessageThread::query()
            ->with(['listing', 'buyer', 'seller'])
            ->findOrFail($id);

        // 404, а не 403: чужой разговор не должен подтверждать
        // само своё существование
        abort_unless($thread->isParticipant($company), 404);

        $thread->markReadFor($company);

        $other = $thread->counterpart($company);

        return Inertia::render('cabinet/Chat', [
            'thread' => [
                'id' => $thread->id,
                'company' => $other?->name ?? 'Компания удалена',
                'initials' => $other?->initials() ?? '—',
                'company_slug' => $other?->slug,
                'listing' => $thread->listing === null ? null : [
                    'title' => $thread->listing->title,
                    'slug' => $thread->listing->slug,
                    'active' => $thread->listing->status === Listing::STATUS_ACTIVE,
                ],
            ],
            'messages' => $thread->messages()
                ->orderBy('id')
                ->limit(500)
                ->get()
                ->map(fn (Message $m): array => [
                    'id' => $m->id,
                    'mine' => $m->company_id === $company->id,
                    'body' => $m->body,
                    'at' => $m->created_at->translatedFormat('d.m.Y H:i'),
                ]),
        ]);
    }

    public function send(Request $request, int $id): RedirectResponse
    {
        $company = $request->user()->company;
        abort_if($company === null, 404);

        $thread = MessageThread::query()->findOrFail($id);
        abort_unless($thread->isParticipant($company), 404);

        $data = $request->validate(
            ['body' => ['required', 'string', 'max:'.ChatService::MAX_LENGTH]],
            ['body.required' => 'Введите сообщение', 'body.max' => 'Сообщение слишком длинное'],
        );

        try {
            $this->chat->send($thread, $company, $request->user(), $data['body']);
        } catch (ChatRejected $e) {
            return back()->withErrors(['body' => $e->getMessage()]);
        }

        return back();
    }

    /**
     * Отклик с карточки объявления: создаёт разговор и уводит в него.
     */
    public function respond(Request $request, int $id): RedirectResponse
    {
        $user = $request->user();
        $company = $user->company;

        if ($company === null) {
            return back()->withErrors(['body' => 'Сначала заполните данные компании — отклик отправляется от её имени']);
        }

        $listing = Listing::query()->with('company')->findOrFail($id);

        $data = $request->validate(
            ['body' => ['required', 'string', 'max:'.ChatService::MAX_LENGTH]],
            ['body.required' => 'Напишите, что вас интересует', 'body.max' => 'Сообщение слишком длинное'],
        );

        try {
            $thread = $this->chat->respond($listing, $company, $user, $data['body']);
        } catch (ChatRejected $e) {
            return back()->withErrors(['body' => $e->getMessage()]);
        }

        return redirect()
            ->route('cabinet.chats.show', $thread->id)
            ->with('success', 'Отклик отправлен — продолжайте разговор здесь.');
    }
}
