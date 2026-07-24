import { AlertTriangle } from 'lucide-react';

interface ChartCardProps {
  title: string;
  subtitle?: string;
  sampleSize?: number;
  children: React.ReactNode;
  className?: string;
}

export function ChartCard({ title, subtitle, sampleSize, children, className = '' }: ChartCardProps) {
  return (
    <div className={`bg-white rounded-xl border border-gray-200 p-5 ${className}`}>
      <div className="mb-4">
        <h3 className="text-sm font-semibold text-navy-800">{title}</h3>
        {subtitle && <p className="text-xs text-gray-400 mt-0.5">{subtitle}</p>}
        {sampleSize !== undefined && sampleSize < 10 && (
          <div className="flex items-center gap-1.5 mt-2 text-amber-600 bg-amber-50 rounded-md px-2.5 py-1.5 text-xs">
            <AlertTriangle className="w-3.5 h-3.5 shrink-0" />
            <span>Small sample size (n={sampleSize}). Interpret with caution.</span>
          </div>
        )}
      </div>
      {children}
    </div>
  );
}
