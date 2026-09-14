import { Bot, Code2, Database, Globe, Headset, Palette, Smartphone, Workflow } from 'lucide-react';

import { cn } from '@/lib/cn';

/**
 * Обложка задачи на разработку — по сфере работы.
 *
 * Фотографий у задач нет и взяться им неоткуда: заказчик описывает
 * словами то, чего ещё не существует. Поэтому обложка рисуется —
 * градиент и крупный знак, закреплённые за видом услуги. Тот же приём,
 * что у обложек новостей (NewsCover): одинаковые карточки различаются
 * с первого взгляда, а лента не выглядит недоделанной.
 *
 * Ключи — коды из ItTask::SERVICE_TYPES. Неизвестный код попадает
 * в «прочее»: справочник видов услуг пополняется в коде, и появление
 * нового кода не должно ронять вёрстку ленты.
 */
const STYLES: Record<string, { cls: string; icon: typeof Globe }> = {
    web: { cls: 'cover-web', icon: Globe },
    mobile: { cls: 'cover-mobile', icon: Smartphone },
    erp: { cls: 'cover-erp', icon: Database },
    integration: { cls: 'cover-integration', icon: Workflow },
    design: { cls: 'cover-design', icon: Palette },
    automation: { cls: 'cover-automation', icon: Bot },
    support: { cls: 'cover-support', icon: Headset },
    other: { cls: 'cover-other', icon: Code2 },
};

export function TaskCover({ type, size = 56 }: { type: string; size?: number }) {
    const style = STYLES[type] ?? STYLES.other;
    const Icon = style.icon;

    return (
        <div className={cn('cover-art cover-band', style.cls)} aria-hidden>
            <Icon strokeWidth={1.4} style={{ width: size, height: size }} />
        </div>
    );
}
