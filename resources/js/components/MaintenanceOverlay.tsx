import { usePage } from '@inertiajs/react';
import { Mail, RefreshCw, Send, Wrench } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
import { useBrandLogo } from '@/lib/brand';
import { t } from '@/lib/i18n';
import type { SharedProps } from '@/types';

const pad = (n: number) => String(n).padStart(2, '0');

/**
 * Заставка «Ведутся технические работы» на весь экран.
 *
 * Включается в админке: настройка maintenance_until — время окончания
 * по Ташкенту. Пока оно не наступило, заставка закрывает любую страницу
 * сайта и кабинета, прокрутка под ней заперта. В срок заставка пропадает
 * сама, без перезагрузки. Админка (/py/admin) ею не закрывается — работы
 * можно продлить или снять досрочно.
 */
export function MaintenanceOverlay() {
    const { maintenance, support } = usePage<SharedProps>().props;
    const logo = useBrandLogo();
    const until = useMemo(() => (maintenance ? Date.parse(maintenance.until) : NaN), [maintenance]);
    const [now, setNow] = useState(() => Date.now());

    const left = Number.isFinite(until) ? until - now : 0;
    const active = left > 0;

    useEffect(() => {
        if (!Number.isFinite(until)) return;

        const timer = window.setInterval(() => setNow(Date.now()), 1000);

        return () => window.clearInterval(timer);
    }, [until]);

    // Под заставкой страница не прокручивается и не получает фокус
    useEffect(() => {
        if (!active) return;

        const root = document.documentElement;
        const previous = root.style.overflow;
        root.style.overflow = 'hidden';
        root.classList.add('is-maintenance');

        return () => {
            root.style.overflow = previous;
            root.classList.remove('is-maintenance');
        };
    }, [active]);

    if (!active) return null;

    const seconds = Math.floor(left / 1000);
    const parts = [
        { value: Math.floor(seconds / 3600), label: t('maintenance.hours') },
        { value: Math.floor((seconds % 3600) / 60), label: t('maintenance.minutes') },
        { value: seconds % 60, label: t('maintenance.seconds') },
    ];
    const clock = new Intl.DateTimeFormat('ru-RU', {
        hour: '2-digit',
        minute: '2-digit',
        timeZone: 'Asia/Tashkent',
    }).format(new Date(until));

    return (
        <div className="maint" role="alertdialog" aria-modal="true" aria-labelledby="maint-title" aria-describedby="maint-text">
            <div className="maint-glow maint-glow--a" aria-hidden />
            <div className="maint-glow maint-glow--b" aria-hidden />
            <div className="maint-grid" aria-hidden />

            <div className="maint-card">
                <img src={logo.src} alt="SavdEx" className={logo.custom ? 'maint-logo' : 'maint-logo maint-logo--mono'} />

                <span className="maint-icon" aria-hidden>
                    <Wrench className="size-7" />
                </span>

                <span className="maint-badge">
                    <span className="maint-dot" aria-hidden /> {t('maintenance.badge')}
                </span>

                <h1 id="maint-title" className="maint-title">
                    {t('maintenance.title')}
                </h1>
                <p id="maint-text" className="maint-text">
                    {t('maintenance.text')}
                </p>

                <p className="maint-eta">{t('maintenance.eta')}</p>
                <div className="maint-timer" aria-live="off">
                    {parts.map((part) => (
                        <div key={part.label} className="maint-cell">
                            <b>{pad(part.value)}</b>
                            <small>{part.label}</small>
                        </div>
                    ))}
                </div>

                {/* Полоска без процентов: настройка хранит только конец
                    работ, и честной доли «сделано» не посчитать */}
                <div className="maint-progress" aria-hidden>
                    <span />
                </div>
                <p className="maint-until">{t('maintenance.until', { time: clock })}</p>

                <p className="maint-thanks">{t('maintenance.thanks')}</p>

                {(support.telegram || support.email) && (
                    <div className="maint-contacts">
                        <span>{t('maintenance.contact')}</span>
                        <div className="maint-links">
                            {support.telegram && (
                                <a href={support.telegram} target="_blank" rel="noopener noreferrer">
                                    <Send aria-hidden className="size-4" /> Telegram
                                </a>
                            )}
                            {support.email && (
                                <a href={`mailto:${support.email}`}>
                                    <Mail aria-hidden className="size-4" /> {support.email}
                                </a>
                            )}
                        </div>
                    </div>
                )}

                <button type="button" className="maint-reload" onClick={() => window.location.reload()}>
                    <RefreshCw aria-hidden className="size-4" /> {t('maintenance.reload')}
                </button>
            </div>
        </div>
    );
}
