import { useForm, usePage } from '@inertiajs/react';
import { AlertCircle, Clock, Mail, MessageCircle, Phone } from 'lucide-react';
import type { FormEvent, ReactNode } from 'react';
import { PublicLayout } from '@/layouts/PublicLayout';
import { cn } from '@/lib/cn';
import { t } from '@/lib/i18n';
import { useSupport } from '@/lib/support';
import { routes } from '@/routes';
import type { SharedProps } from '@/types';

/**
 * Контакты площадки.
 *
 * Реквизиты те же, что в разделе «О нас», — телефон, почта и Telegram
 * поддержки из настроек админки. Подписи лежат в словаре и переводятся
 * вместе с остальным интерфейсом.
 *
 * Под реквизитами — форма заявки: она становится лидом в CRM
 * (источник «Форма на сайте»), менеджер видит её на доске лидов.
 */
export default function Contacts() {
    const support = useSupport();

    const cards: [typeof Mail, string, string, string | null][] = [
        [Phone, t('contacts.phone_title'), support.phone, support.telHref],
        [Mail, t('contacts.email_title'), support.email, `mailto:${support.email}`],
        [MessageCircle, t('contacts.tg_title'), support.tgHandle, support.telegram],
        [Clock, t('contacts.hours_title'), support.hours || t('contacts.hours_value'), null],
    ];

    return (
        <PublicLayout title={t('contacts.meta_title')} description={t('contacts.meta_description')}>
            <div className="container" style={{ paddingBlock: '32px 96px', maxWidth: 960 }}>
                <div className="section-head-left" style={{ marginBottom: 24 }}>
                    <span className="eyebrow">{t('contacts.eyebrow')}</span>
                    <h1 className="t-section">{t('contacts.h1')}</h1>
                    <p className="t-lead">{t('contacts.lead')}</p>
                </div>

                <div className="grid grid-2" data-reveal-stagger>
                    {cards.map(([Icon, title, value, href]) => (
                        <div key={title} className="card row" style={{ gap: 16, alignItems: 'flex-start' }}>
                            <span className="ico-box ico-box-lg">
                                <Icon aria-hidden className="size-5" />
                            </span>
                            <div style={{ minWidth: 0 }}>
                                <h2 className="t-h4" style={{ marginBottom: 4 }}>
                                    {title}
                                </h2>
                                {href ? (
                                    // contact-value: на тач-устройствах строка ссылки
                                    // вырастает до 44 px — по телефону звонят с мобильного
                                    <a href={href} className="t-body contact-value" style={{ overflowWrap: 'anywhere' }}>
                                        {value}
                                    </a>
                                ) : (
                                    <p className="t-body" style={{ overflowWrap: 'anywhere' }}>{value}</p>
                                )}
                            </div>
                        </div>
                    ))}
                </div>

                <RequestForm />

                <div className="alert alert-info mt-32">
                    <Mail aria-hidden className="size-5" />
                    <div>
                        <b>{t('contacts.note_bold')}</b> {t('contacts.note_text')}
                    </div>
                </div>
            </div>
        </PublicLayout>
    );
}

type RequestData = { name: string; phone: string; email: string; company: string; message: string; website: string };

/**
 * Заявка → лид. Вошедшему имя и почта подставлены из учётной записи.
 * Поле website скрыто от людей: его заполняют только боты, и такая
 * заявка лидом не становится.
 */
function RequestForm() {
    const user = usePage<SharedProps>().props.auth?.user ?? null;
    const { data, setData, post, processing, errors, reset } = useForm<RequestData>({
        name: user?.name ?? '',
        phone: '',
        email: user?.email ?? '',
        company: '',
        message: '',
        website: '',
    });

    function submit(e: FormEvent) {
        e.preventDefault();
        post(routes.contacts, { preserveScroll: true, onSuccess: () => reset('message') });
    }

    function field(key: keyof RequestData, label: string, control: ReactNode, required = false) {
        return (
            // Отступ между полями задаёт сетка: .field + .field сдвигал бы правую колонку
            <div className={cn('field', errors[key] && 'is-error')} style={{ marginTop: 0 }}>
                <label className="label" htmlFor={`request-${key}`}>
                    {label}
                    {required && <span className="req"> *</span>}
                </label>
                {control}
                {errors[key] && (
                    <p className="error-text" id={`request-${key}-error`}>
                        <AlertCircle aria-hidden className="size-3.5" />
                        <span>{errors[key]}</span>
                    </p>
                )}
            </div>
        );
    }

    function input(key: Exclude<keyof RequestData, 'message' | 'website'>, type: string, autoComplete: string, max: number) {
        return (
            <input
                id={`request-${key}`}
                className="input"
                type={type}
                name={key}
                autoComplete={autoComplete}
                maxLength={max}
                value={data[key]}
                onChange={(e) => setData(key, e.target.value)}
                aria-invalid={errors[key] ? true : undefined}
                aria-describedby={errors[key] ? `request-${key}-error` : undefined}
            />
        );
    }

    return (
        <section className="card mt-32" aria-labelledby="request-title">
            <h2 id="request-title" className="t-h3" style={{ marginBottom: 4 }}>
                {t('contacts.form_title')}
            </h2>
            <p className="t-body text-muted" style={{ marginBottom: 20 }}>
                {t('contacts.form_lead')}
            </p>

            <form onSubmit={submit} noValidate>
                <div className="grid grid-2" style={{ gap: 20 }}>
                    {field('name', t('contacts.form_name'), input('name', 'text', 'name', 160), true)}
                    {field('company', t('contacts.form_company'), input('company', 'text', 'organization', 190))}
                    {field('phone', t('contacts.form_phone'), input('phone', 'tel', 'tel', 40))}
                    {field('email', t('contacts.form_email'), input('email', 'email', 'email', 160))}
                </div>
                {!errors.phone && <p className="hint">{t('contacts.form_reach_hint')}</p>}

                <div className="mt-16">
                    {field(
                        'message',
                        t('contacts.form_message'),
                        <textarea
                            id="request-message"
                            className="textarea"
                            name="message"
                            maxLength={2000}
                            placeholder={t('contacts.form_message_placeholder')}
                            value={data.message}
                            onChange={(e) => setData('message', e.target.value)}
                            aria-invalid={errors.message ? true : undefined}
                            aria-describedby={errors.message ? 'request-message-error' : undefined}
                        />,
                        true,
                    )}
                </div>

                {/* Ловушка для ботов: человек это поле не видит */}
                <div aria-hidden="true" style={{ position: 'absolute', left: -10000, width: 1, height: 1, overflow: 'hidden' }}>
                    <label htmlFor="request-website">Website</label>
                    <input
                        id="request-website"
                        name="website"
                        tabIndex={-1}
                        autoComplete="off"
                        value={data.website}
                        onChange={(e) => setData('website', e.target.value)}
                    />
                </div>

                <button type="submit" className="btn btn-primary mt-16" disabled={processing}>
                    {processing ? t('contacts.form_sending') : t('contacts.form_send')}
                </button>
            </form>
        </section>
    );
}
