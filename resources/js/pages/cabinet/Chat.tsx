import { router, useForm } from '@inertiajs/react';
import { Link } from '@/components/ui/Link';
import { ArrowLeft, SendHorizontal } from 'lucide-react';
import { useEffect, useRef, type FormEvent } from 'react';
import { CabinetLayout } from '@/layouts/CabinetLayout';
import { routes } from '@/routes';

interface Msg {
    id: number;
    mine: boolean;
    body: string;
    at: string;
}

interface ThreadInfo {
    id: number;
    company: string;
    initials: string;
    company_slug: string | null;
    listing: { title: string; slug: string | null; active: boolean } | null;
}

/**
 * Разговор с компанией.
 *
 * Живёт без вебсокетов: раз в десять секунд частично перезапрашиваются
 * только сообщения. Для переписки о поставках этого достаточно, а на
 * хостинге без постоянных соединений это единственный честный вариант.
 */
export default function Chat({ thread, messages }: { thread: ThreadInfo; messages: Msg[] }) {
    const scrollRef = useRef<HTMLDivElement>(null);
    const lastId = messages.length > 0 ? messages[messages.length - 1].id : 0;
    const form = useForm({ body: '' });

    useEffect(() => {
        const id = setInterval(
            () => router.reload({ only: ['messages'] }),
            10_000,
        );

        return () => clearInterval(id);
    }, []);

    // Вниз — при открытии и на каждом новом сообщении
    useEffect(() => {
        scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight });
    }, [lastId]);

    function submit(e: FormEvent) {
        e.preventDefault();

        if (form.data.body.trim() === '') {
            return;
        }

        form.post(routes.cabinetChat(thread.id), {
            preserveScroll: true,
            onSuccess: () => form.reset('body'),
        });
    }

    return (
        <CabinetLayout
            title={`Чат — ${thread.company}`}
            heading={thread.company}
            subheading={thread.listing ? `Объявление: ${thread.listing.title}` : 'Переписка с компанией'}
            actions={
                <Link href={routes.cabinetChats} className="btn btn-secondary btn-sm">
                    <ArrowLeft aria-hidden className="size-4" /> Все чаты
                </Link>
            }
        >
            <div className="card chat-box">
                {thread.listing?.slug && (
                    <p className="t-caption muted" style={{ marginBottom: 12 }}>
                        {thread.listing.active ? (
                            <Link href={routes.listing(thread.listing.slug)}>{thread.listing.title}</Link>
                        ) : (
                            <>{thread.listing.title} · снято с публикации</>
                        )}
                    </p>
                )}

                <div ref={scrollRef} className="chat-scroll" aria-live="polite">
                    {messages.map((m) => (
                        <div key={m.id} className={m.mine ? 'chat-msg is-mine' : 'chat-msg'}>
                            <p className="chat-msg-body">{m.body}</p>
                            <span className="chat-msg-at">{m.at}</span>
                        </div>
                    ))}
                </div>

                <form onSubmit={submit} className="chat-compose">
                    <textarea
                        className="textarea"
                        rows={2}
                        maxLength={2000}
                        placeholder="Сообщение…"
                        value={form.data.body}
                        onChange={(e) => form.setData('body', e.target.value)}
                        onKeyDown={(e) => {
                            if (e.key === 'Enter' && !e.shiftKey) {
                                e.preventDefault();
                                submit(e);
                            }
                        }}
                    />
                    <button
                        type="submit"
                        className="btn btn-primary"
                        aria-label="Отправить"
                        disabled={form.processing || form.data.body.trim() === ''}
                    >
                        <SendHorizontal aria-hidden className="size-4" />
                    </button>
                </form>
                {form.errors.body && (
                    <p className="hint" style={{ color: 'var(--danger)' }}>
                        {form.errors.body}
                    </p>
                )}
                <p className="t-caption muted mt-8">
                    Телефоны, почта и ссылки в сообщениях автоматически скрываются — контакты передаются через
                    раскрытие контактов.
                </p>
            </div>
        </CabinetLayout>
    );
}
