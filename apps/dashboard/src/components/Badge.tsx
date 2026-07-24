import { X } from 'lucide-react';

const variants = {
  default: 'bg-gray-100 text-gray-700',
  primary: 'bg-accent-50 text-accent-700',
  success: 'bg-emerald-50 text-emerald-700',
  warning: 'bg-amber-50 text-amber-700',
  danger: 'bg-red-50 text-red-700',
  info: 'bg-sky-50 text-sky-700',
} as const;

interface BadgeProps {
  children: React.ReactNode;
  variant?: keyof typeof variants;
  className?: string;
  onRemove?: () => void;
}

export function Badge({ children, variant = 'default', className = '', onRemove }: BadgeProps) {
  return (
    <span
      className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-xs font-medium ${variants[variant]} ${className}`}
    >
      <span>{children}</span>
      {onRemove && (
        <button
          type="button"
          onClick={(e) => {
            e.stopPropagation();
            onRemove();
          }}
          className="hover:opacity-75 focus:outline-none cursor-pointer"
          aria-label="Remove badge filter"
        >
          <X className="w-3 h-3" />
        </button>
      )}
    </span>
  );
}
