import { ChevronDown, ChevronUp, ChevronsUpDown } from 'lucide-react';

export interface Column<T> {
  key: string;
  header: string;
  render: (item: T, index: number) => React.ReactNode;
  sortable?: boolean;
  className?: string;
  hideOnMobile?: boolean;
}

interface DataTableProps<T> {
  columns: Column<T>[];
  data: T[];
  keyExtractor: (item: T) => string | number;
  onRowClick?: (item: T) => void;
  sortKey?: string;
  sortOrder?: 'asc' | 'desc';
  onSort?: (key: string) => void;
  emptyMessage?: string;
}

export function DataTable<T>({
  columns,
  data,
  keyExtractor,
  onRowClick,
  sortKey,
  sortOrder,
  onSort,
  emptyMessage = 'No data available',
}: DataTableProps<T>) {
  function renderSortIcon(key: string) {
    if (sortKey !== key) return <ChevronsUpDown className="w-3.5 h-3.5 text-gray-300" />;
    return sortOrder === 'asc' ? (
      <ChevronUp className="w-3.5 h-3.5 text-accent-600" />
    ) : (
      <ChevronDown className="w-3.5 h-3.5 text-accent-600" />
    );
  }

  if (data.length === 0) {
    return (
      <div className="text-center py-12 text-gray-400 text-sm">{emptyMessage}</div>
    );
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-gray-100">
            {columns.map((col) => (
              <th
                key={col.key}
                className={`text-left py-3 px-3 text-xs font-semibold text-gray-500 uppercase tracking-wider ${col.hideOnMobile ? 'hidden md:table-cell' : ''} ${col.sortable ? 'cursor-pointer select-none hover:text-navy-700' : ''} ${col.className || ''}`}
                onClick={() => col.sortable && onSort?.(col.key)}
              >
                <div className="flex items-center gap-1">
                  {col.header}
                  {col.sortable && renderSortIcon(col.key)}
                </div>
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-50">
          {data.map((item, rowIndex) => (
            <tr
              key={keyExtractor(item)}
              className={`hover:bg-gray-50/50 transition-colors ${onRowClick ? 'cursor-pointer' : ''}`}
              onClick={() => onRowClick?.(item)}
            >
              {columns.map((col) => (
                <td
                  key={col.key}
                  className={`py-3 px-3 text-navy-700 ${col.hideOnMobile ? 'hidden md:table-cell' : ''} ${col.className || ''}`}
                >
                  {col.render(item, rowIndex)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
