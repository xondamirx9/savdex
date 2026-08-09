import { Clock, Mail, MessageCircle, Phone } from 'lucide-react';
import { PublicLayout } from '@/layouts/PublicLayout';
import { t } from '@/lib/i18n';

/**
 * Контакты площадки.
 *
 * Реквизиты те же, что в разделе «О нас», — телефон, почта и Telegram
 * поддержки. Подписи лежат в словаре и переводятся вместе с остальным
 * интерфейсом.
 */
export default function Contacts() {
    const cards: [typeof Mail, string, string, string | null][] = [
        [Phone, t('contacts.phone_title'), '+998 71 200-00-00', 'tel:+998712000000'],
        [Mail, t('contacts.email_title'), 'support@savdex.uz', 'mailto:support@savdex.uz'],
        [MessageCircle, t('contacts.tg_title'), '@savdex_support', 'https://t.me/savdex_support'],
        [Clock, t('contacts.hours_title'), t('contacts.hours_value'), null],
    ];

    return (
        <PublicLayout title={t('contacts.meta_title')} description={t('contacts.meta_description')}>
            <div className="container" style={{ padding: '32px 0 96px', maxWidth: 960 }}>
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
                                    <a href={href} className="t-body" style={{ overflowWrap: 'anywhere' }}>
                                        {value}
                                    </a>
                                ) : (
                                    <p className="t-body" style={{ overflowWrap: 'anywhere' }}>{value}</p>
                                )}
                            </div>
                        </div>
                    ))}
                </div>

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
