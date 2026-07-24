import { Search, X } from 'lucide-react';
import { useRef } from 'react';

interface SearchInputProps {
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  className?: string;
}

export function SearchInput({ value, onChange, placeholder = 'Search...', className = '' }: SearchInputProps) {
  const ref = useRef<HTMLInputElement>(null);
  return (
    <div className={`relative ${className}`}>
      <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
      <input
        ref={ref}
        type="text"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        className="w-full pl-9 pr-8 py-2 text-sm border border-gray-200 rounded-lg bg-white text-navy-800 placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-accent-500/20 focus:border-accent-400 transition-colors"
      />
      {value && (
        <button
          onClick={() => { onChange(''); ref.current?.focus(); }}
          className="absolute right-2.5 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600"
          aria-label="Clear search"
        >
          <X className="w-3.5 h-3.5" />
        </button>
      )}
    </div>
  );
}
