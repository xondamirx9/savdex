import { Crown, Handshake, Landmark, type LucideIcon } from 'lucide-react';

/** Вид партнёров — он же часть адреса страницы: /partners/general. */
export type PartnerTierSlug = 'general' | 'regular' | 'multi';

/** Порядок видов — в ячейках раздела и в меню шапки. */
export const PARTNER_TIERS: PartnerTierSlug[] = ['general', 'regular', 'multi'];

/** Значок и цвет вида — общие для раздела, страниц видов и меню. */
export const TIER_LOOK: Record<PartnerTierSlug, [LucideIcon, string]> = {
    general: [Crown, 'stat-ico-violet'],
    regular: [Handshake, 'stat-ico-blue'],
    multi: [Landmark, 'stat-ico-sky'],
};
