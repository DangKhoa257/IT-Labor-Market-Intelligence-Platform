import { ChevronLeft, ChevronRight } from 'lucide-react';

interface PaginationProps {
  page: number;
  pages: number;
  total: number;
  pageSize: number;
  onPageChange: (page: number) => void;
}

export function Pagination({ page, pages, total, pageSize, onPageChange }: PaginationProps) {
  const start = (page - 1) * pageSize + 1;
  const end = Math.min(page * pageSize, total);

  return (
    <div className="flex items-center justify-between py-3 px-1">
      <p className="text-sm text-gray-500">
        Showing <span className="font-medium text-navy-700">{start}</span>–
        <span className="font-medium text-navy-700">{end}</span> of{' '}
        <span className="font-medium text-navy-700">{total}</span>
      </p>
      <div className="flex items-center gap-1">
        <button
          onClick={() => onPageChange(page - 1)}
          disabled={page <= 1}
          className="p-1.5 rounded-md border border-gray-200 text-gray-500 hover:bg-gray-50 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
          aria-label="Previous page"
        >
          <ChevronLeft className="w-4 h-4" />
        </button>
        {Array.from({ length: Math.min(pages, 5) }, (_, i) => {
          let pageNum: number;
          if (pages <= 5) {
            pageNum = i + 1;
          } else if (page <= 3) {
            pageNum = i + 1;
          } else if (page >= pages - 2) {
            pageNum = pages - 4 + i;
          } else {
            pageNum = page - 2 + i;
          }
          return (
            <button
              key={pageNum}
              onClick={() => onPageChange(pageNum)}
              className={`w-8 h-8 rounded-md text-sm font-medium transition-colors ${
                pageNum === page
                  ? 'bg-accent-600 text-white'
                  : 'text-gray-600 hover:bg-gray-100'
              }`}
              aria-label={`Page ${pageNum}`}
              aria-current={pageNum === page ? 'page' : undefined}
            >
              {pageNum}
            </button>
          );
        })}
        <button
          onClick={() => onPageChange(page + 1)}
          disabled={page >= pages}
          className="p-1.5 rounded-md border border-gray-200 text-gray-500 hover:bg-gray-50 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
          aria-label="Next page"
        >
          <ChevronRight className="w-4 h-4" />
        </button>
      </div>
    </div>
  );
}
