import type { LucideIcon } from 'lucide-react';

interface StatCardProps {
  label: string;
  value: string | number;
  subtitle?: string;
  icon?: LucideIcon;
  trend?: 'up' | 'down' | 'neutral';
}

export function StatCard({ label, value, subtitle, icon: Icon }: StatCardProps) {
  return (
    <div className="bg-white rounded-xl border border-gray-200 p-5 hover:shadow-sm transition-shadow">
      <div className="flex items-start justify-between">
        <div className="space-y-1">
          <p className="text-sm font-medium text-gray-500">{label}</p>
          <p className="text-2xl font-semibold text-navy-800 tracking-tight">{value}</p>
          {subtitle && <p className="text-xs text-gray-400">{subtitle}</p>}
        </div>
        {Icon && (
          <div className="p-2.5 bg-accent-50 rounded-lg">
            <Icon className="w-5 h-5 text-accent-600" />
          </div>
        )}
      </div>
    </div>
  );
}
