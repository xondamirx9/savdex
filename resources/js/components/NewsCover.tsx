import { BarChart3, Lightbulb, Rocket, Wallet } from 'lucide-react';
import { cn } from '@/lib/cn';

/**
 * Обложка новости.
 *
 * Своих фотографий пока нет, а серый прямоугольник с надписью «нет фото»
 * выглядит как недоделка. Вместо него — градиент, детерминированно
 * выбранный по рубрике, и крупная иконка. Читается как осознанное
 * оформление, а не как отсутствие картинки.
 *
 * Когда появится загрузка обложек, компонент будет отдавать <img>,
 * а градиент останется запасным вариантом для публикаций без фото.
 */

const STYLES: Record<string, { cls: string; icon: typeof Rocket }> = {
    'Обновления сервиса': { cls: 'cover-updates', icon: Rocket },
    'Тарифы и оплата': { cls: 'cover-pricing', icon: Wallet },
    'Аналитика рынка': { cls: 'cover-analytics', icon: BarChart3 },
    Полезное: { cls: 'cover-useful', icon: Lightbulb },
};

export function NewsCover({
    category,
    image,
    tall = false,
    size = 44,
}: {
    category: string;
    image?: string | null;
    tall?: boolean;
    size?: number;
}) {
    const style = STYLES[category] ?? STYLES['Обновления сервиса'];
    const Icon = style.icon;

    if (image) {
        return (
            <div className={cn('cover-art', tall && 'cover-art-tall')}>
                <img src={image} alt="" className="size-full object-cover" loading="lazy" />
            </div>
        );
    }

    return (
        <div className={cn('cover-art', tall && 'cover-art-tall', style.cls)} aria-hidden>
            <Icon strokeWidth={1.4} style={{ width: size, height: size }} />
        </div>
    );
}
