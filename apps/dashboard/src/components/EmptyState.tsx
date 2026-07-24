import { Inbox } from 'lucide-react';
import type { LucideIcon } from 'lucide-react';

interface EmptyStateProps {
  icon?: LucideIcon;
  title: string;
  description?: string;
  action?: React.ReactNode;
}

export function EmptyState({ icon: Icon = Inbox, title, description, action }: EmptyStateProps) {
  return (
    <div className="flex flex-col items-center justify-center py-16 text-center">
      <div className="p-3 bg-gray-100 rounded-xl mb-4">
        <Icon className="w-6 h-6 text-gray-400" />
      </div>
      <h3 className="text-sm font-semibold text-navy-700 mb-1">{title}</h3>
      {description && <p className="text-xs text-gray-400 max-w-xs">{description}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}
