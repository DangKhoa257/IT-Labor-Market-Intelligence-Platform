import { AlertCircle, RefreshCw } from 'lucide-react';

interface ErrorStateProps {
  title?: string;
  message?: string;
  onRetry?: () => void;
}

export function ErrorState({
  title = 'Failed to load data',
  message = 'An error occurred while fetching data from the API.',
  onRetry,
}: ErrorStateProps) {
  return (
    <div className="flex flex-col items-center justify-center py-16 text-center">
      <div className="p-3 bg-red-50 rounded-xl mb-4">
        <AlertCircle className="w-6 h-6 text-red-500" />
      </div>
      <h3 className="text-sm font-semibold text-navy-700 mb-1">{title}</h3>
      <p className="text-xs text-gray-400 max-w-xs">{message}</p>
      {onRetry && (
        <button
          onClick={onRetry}
          className="mt-4 inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-accent-700 bg-accent-50 rounded-md hover:bg-accent-100 transition-colors"
        >
          <RefreshCw className="w-3.5 h-3.5" />
          Retry
        </button>
      )}
    </div>
  );
}
