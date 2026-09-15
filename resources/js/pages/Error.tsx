import { Link } from '@/components/ui/Link';
import { Ban, Clock, Compass, ServerCrash, Wrench } from 'lucide-react';
import { PublicLayout } from '@/layouts/PublicLayout';
import { t } from '@/lib/i18n';
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
    /** Ключ в словаре: заголовок и текст берутся из него при отрисовке. */
    key: string;
    actions: { href: string; label: string; primary?: boolean }[];
}

/**
 * Подписи кнопок — ключи словаря, а не готовые строки: набор
 * констант вычисляется при загрузке модуля, когда словарь ещё
 * не пришёл, поэтому переводится он внутри компонента.
 */
const PRESETS: Record<number, Preset> = {
    404: {
        icon: Compass,
        tone: '',
        key: 'e404',
        actions: [
            { href: routes.companies, label: 'companies', primary: true },
            { href: routes.home, label: 'home' },
        ],
    },
    403: {
        icon: Ban,
        tone: 'ico-box-warning',
        key: 'e403',
        actions: [
            { href: routes.cabinet, label: 'cabinet', primary: true },
            { href: routes.home, label: 'home' },
        ],
    },
    419: {
        icon: Clock,
        tone: 'ico-box-warning',
        key: 'e419',
        actions: [
            { href: routes.login, label: 'login', primary: true },
            { href: routes.home, label: 'home' },
        ],
    },
    429: {
        icon: Clock,
        tone: 'ico-box-warning',
        key: 'e429',
        actions: [{ href: routes.home, label: 'home', primary: true }],
    },
    500: {
        icon: ServerCrash,
        tone: 'ico-box-danger',
        key: 'e500',
        actions: [{ href: routes.home, label: 'home', primary: true }],
    },
    503: {
        icon: Wrench,
        tone: 'ico-box-warning',
        key: 'e503',
        actions: [{ href: routes.home, label: 'reload', primary: true }],
    },
};

export default function ErrorPage({ status, reference }: { status: number; reference?: string }) {
    const preset = PRESETS[status] ?? PRESETS[500];
    const Icon = preset.icon;
    const support = useSupport();

    return (
        <PublicLayout title={`${status} — ${t(`error_page.${preset.key}_title`)}`}>
            <div className="container" style={{ paddingBlock: '64px 96px' }}>
                <div className="empty" style={{ maxWidth: 520 }}>
                    <div className={`empty-icon ${preset.tone}`}>
                        <Icon aria-hidden className="size-8" />
                    </div>

                    <p className="t-caption muted" style={{ letterSpacing: '.08em' }}>
                        {t('error_page.code', { status })}
                    </p>
                    <h1 className="t-h1" style={{ marginTop: 8, marginBottom: 12 }}>
                        {t(`error_page.${preset.key}_title`)}
                    </h1>
                    <p>{t(`error_page.${preset.key}_text`)}</p>

                    <div className="row" style={{ justifyContent: 'center', gap: 10, flexWrap: 'wrap' }}>
                        {preset.actions.map((a) => (
                            <Link key={a.href + a.label} href={a.href} className={`btn ${a.primary ? 'btn-primary' : 'btn-secondary'}`}>
                                {t(`error_page.${a.label}`)}
                            </Link>
                        ))}
                    </div>

                    {/* Код обращения нужен, чтобы поддержка нашла конкретный лог,
                        а не спрашивала «а что вы делали» */}
                    {reference && (
                        <p className="t-caption muted mt-24" style={{ fontFamily: 'ui-monospace, monospace' }}>
                            {t('error_page.reference', { reference })}
                        </p>
                    )}

                    <p className="t-sm muted mt-16">
                        {t('error_page.help')} <a href={`mailto:${support.email}`}>{support.email}</a>
                    </p>
                </div>
            </div>
        </PublicLayout>
    );
}
