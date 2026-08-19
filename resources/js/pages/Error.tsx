import { Link } from '@/components/ui/Link';
import { Ban, Clock, Compass, ServerCrash, Wrench } from 'lucide-react';
import { PublicLayout } from '@/layouts/PublicLayout';
import { useSupport } from '@/lib/support';
import { routes } from '@/routes';

/**
 * Страница ошибки для пользователя, а не для разработчика.
 *
 * Каждое сообщение отвечает на три вопроса: что случилось, кто виноват
 * и что делать дальше. Тупиков нет — с любой ошибки есть выход
 * (правило 8 из §1 QA.md).
 */

interface Preset {
    icon: typeof Compass;
    tone: string;
    title: string;
    text: string;
    actions: { href: string; label: string; primary?: boolean }[];
}

const PRESETS: Record<number, Preset> = {
    404: {
        icon: Compass,
        tone: '',
        title: 'Такой страницы нет',
        text: 'Возможно, объявление снято с публикации, компания удалила профиль или в адресе опечатка.',
        actions: [
            { href: routes.companies, label: 'Смотреть компании', primary: true },
            { href: routes.home, label: 'На главную' },
        ],
    },
    403: {
        icon: Ban,
        tone: 'ico-box-warning',
        title: 'Доступ закрыт',
        text: 'У вашей учётной записи нет прав на этот раздел. Если доступ нужен по работе, попросите владельца компании выдать его в разделе «Сотрудники».',
        actions: [
            { href: routes.cabinet, label: 'В кабинет', primary: true },
            { href: routes.home, label: 'На главную' },
        ],
    },
    419: {
        icon: Clock,
        tone: 'ico-box-warning',
        title: 'Страница устарела',
        text: 'Вы слишком долго заполняли форму, и сессия закрылась в целях безопасности. Войдите заново — введённые данные придётся ввести ещё раз.',
        actions: [
            { href: routes.login, label: 'Войти', primary: true },
            { href: routes.home, label: 'На главную' },
        ],
    },
    429: {
        icon: Clock,
        tone: 'ico-box-warning',
        title: 'Слишком много запросов',
        text: 'Вы отправили много запросов подряд, и мы временно ограничили доступ. Подождите минуту и попробуйте снова.',
        actions: [{ href: routes.home, label: 'На главную', primary: true }],
    },
    500: {
        icon: ServerCrash,
        tone: 'ico-box-danger',
        title: 'Что-то сломалось у нас',
        text: 'Это ошибка на нашей стороне, а не у вас. Она уже записана, инженеры уведомлены. Попробуйте обновить страницу через минуту.',
        actions: [{ href: routes.home, label: 'На главную', primary: true }],
    },
    503: {
        icon: Wrench,
        tone: 'ico-box-warning',
        title: 'Идут технические работы',
        text: 'Площадка ненадолго недоступна — обновляем сервис. Каталог и объявления вернутся в течение нескольких минут.',
        actions: [{ href: routes.home, label: 'Обновить', primary: true }],
    },
};

export default function ErrorPage({ status, reference }: { status: number; reference?: string }) {
    const preset = PRESETS[status] ?? PRESETS[500];
    const Icon = preset.icon;
    const support = useSupport();

    return (
        <PublicLayout title={`${status} — ${preset.title}`}>
            <div className="container" style={{ padding: '64px 0 96px' }}>
                <div className="empty" style={{ maxWidth: 520 }}>
                    <div className={`empty-icon ${preset.tone}`}>
                        <Icon aria-hidden className="size-8" />
                    </div>

                    <p className="t-caption muted" style={{ letterSpacing: '.08em' }}>
                        ОШИБКА {status}
                    </p>
                    <h1 className="t-h1" style={{ marginTop: 8, marginBottom: 12 }}>
                        {preset.title}
                    </h1>
                    <p>{preset.text}</p>

                    <div className="row" style={{ justifyContent: 'center', gap: 10, flexWrap: 'wrap' }}>
                        {preset.actions.map((a) => (
                            <Link key={a.href + a.label} href={a.href} className={`btn ${a.primary ? 'btn-primary' : 'btn-secondary'}`}>
                                {a.label}
                            </Link>
                        ))}
                    </div>

                    {/* Код обращения нужен, чтобы поддержка нашла конкретный лог,
                        а не спрашивала «а что вы делали» */}
                    {reference && (
                        <p className="t-caption muted mt-24" style={{ fontFamily: 'ui-monospace, monospace' }}>
                            Код обращения: {reference}
                        </p>
                    )}

                    <p className="t-sm muted mt-16">
                        Не помогло? Напишите на <a href={`mailto:${support.email}`}>{support.email}</a>
                    </p>
                </div>
            </div>
        </PublicLayout>
    );
}
