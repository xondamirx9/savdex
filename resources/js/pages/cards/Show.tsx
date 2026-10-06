import { ArrowRight, Mail, Phone } from 'lucide-react';
import { BusinessCard, type CardData } from '@/components/BusinessCard';
import { PublicLayout } from '@/layouts/PublicLayout';
import { t } from '@/lib/i18n';

interface Props {
    card: CardData & { url: string };
    company: { name: string; url: string; logo: string | null };
}

/**
 * Страница визитки — её открывает QR-код.
 *
 * Сначала сама визитка, под ней кнопка на страницу компании-владельца.
 * У собранной визитки почта и телефон уже ссылки на самой карточке;
 * у фото — текст на снимке нажать нельзя, поэтому для него отдельных
 * кнопок звонка нет: контакты есть на странице компании.
 */
export default function CardShow({ card, company }: Props) {
    const name = card.full_name ?? card.company_name ?? company.name;
    const phone = card.phone?.replace(/[^\d+]/g, '');

    return (
        <PublicLayout title={t('cards.page_title', { name })}>
            <div className="biz-card-page">
                <BusinessCard card={card} links />

                {card.kind === 'generated' && (phone || card.email) && (
                    <div className="row wrap" style={{ gap: 10 }}>
                        {phone && (
                            <a href={`tel:${phone}`} className="btn btn-secondary" style={{ flex: 1 }}>
                                <Phone aria-hidden className="size-4" /> {t('cards.call')}
                            </a>
                        )}
                        {card.email && (
                            <a href={`mailto:${card.email}`} className="btn btn-secondary" style={{ flex: 1 }}>
                                <Mail aria-hidden className="size-4" /> {t('cards.write')}
                            </a>
                        )}
                    </div>
                )}

                <a href={company.url} className="btn btn-primary btn-lg btn-block">
                    {t('cards.go_company')} <ArrowRight aria-hidden className="size-4" />
                </a>

                <div className="row" style={{ gap: 10, justifyContent: 'center' }}>
                    {company.logo && (
                        <img src={company.logo} alt="" width={28} height={28} style={{ borderRadius: 6, objectFit: 'cover' }} />
                    )}
                    <span className="t-sm muted">
                        {t('cards.on_platform')}: <b>{company.name}</b>
                    </span>
                </div>
            </div>
        </PublicLayout>
    );
}
