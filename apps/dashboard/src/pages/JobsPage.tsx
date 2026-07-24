import { useSearchParams, useNavigate } from 'react-router-dom';
import { useJobs } from '../hooks/useApi';
import { PageHeader } from '../components/PageHeader';
import { SearchInput } from '../components/SearchInput';
import { Badge } from '../components/Badge';
import { DataTable, type Column } from '../components/DataTable';
import { TableSkeleton } from '../components/LoadingSkeleton';
import { EmptyState } from '../components/EmptyState';
import { ErrorState } from '../components/ErrorState';
import { Pagination } from '../components/Pagination';
import { StatusBadge } from '../components/StatusBadge';
import { formatSalaryRange, formatDate } from '../utils/format';
import type { JobOut } from '../types/api';

export function JobsPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const navigate = useNavigate();

  const page = parseInt(searchParams.get('page') || '1', 10);
  const keyword = searchParams.get('keyword') || '';
  const category = searchParams.get('category') || '';
  const city = searchParams.get('city') || '';
  const work_mode = searchParams.get('work_mode') || '';
  const employment_type = searchParams.get('employment_type') || '';
  const status = searchParams.get('status') || '';
  const salary_disclosed = searchParams.get('salary_disclosed') || '';

  const salaryDisclosedBool =
    salary_disclosed === 'true' ? true : salary_disclosed === 'false' ? false : undefined;

  const { data, isLoading, error } = useJobs({
    page,
    keyword: keyword || undefined,
    category: category || undefined,
    city: city || undefined,
    work_mode: work_mode || undefined,
    employment_type: employment_type || undefined,
    status: status || undefined,
    salary_disclosed: salaryDisclosedBool,
  });

  const updateFilter = (key: string, value: string) => {
    const newParams = new URLSearchParams(searchParams);
    if (value) {
      newParams.set(key, value);
    } else {
      newParams.delete(key);
    }
    if (key !== 'page') newParams.set('page', '1');
    setSearchParams(newParams);
  };

  const clearFilters = () => {
    setSearchParams(new URLSearchParams());
  };

  const hasFilters =
    Boolean(keyword || category || city || work_mode || employment_type || status || salary_disclosed);

  const columns: Column<JobOut>[] = [
    {
      key: 'title',
      header: 'Title',
      render: (row) => (
        <div>
          <p className="font-semibold text-navy-900">{row.title_normalized || row.title_raw}</p>
          {row.title_normalized && (
            <p className="text-xs text-gray-400 font-mono">Raw: {row.title_raw}</p>
          )}
        </div>
      ),
    },
    {
      key: 'category',
      header: 'Category',
      render: (row) => (
        <span className="text-xs text-gray-600 bg-gray-100 px-2 py-0.5 rounded font-medium">
          {row.primary_category || 'Unclassified'}
        </span>
      ),
    },
    {
      key: 'city',
      header: 'City',
      render: (row) => row.city || 'Unspecified',
    },
    {
      key: 'salary',
      header: 'Disclosed Salary',
      render: (row) => formatSalaryRange(row.salary_min, row.salary_max, row.salary_currency),
    },
    {
      key: 'status',
      header: 'Status',
      render: (row) => <StatusBadge status={row.status} />,
    },
    {
      key: 'posted',
      header: 'Posted Date',
      render: (row) => formatDate(row.posted_at),
    },
  ];

  return (
    <div className="space-y-6 pb-12">
      <PageHeader title="Job Explorer" description="Filter and inspect individual job postings ingested from TopDev." />

      <div className="space-y-4 bg-white p-4 rounded-xl shadow-sm border border-gray-200">
        <div className="flex flex-col md:flex-row gap-3">
          <div className="flex-1">
            <SearchInput
              value={keyword}
              onChange={(v) => updateFilter('keyword', v)}
              placeholder="Search by title keyword..."
            />
          </div>
          <select
            value={status}
            onChange={(e) => updateFilter('status', e.target.value)}
            className="text-sm border border-gray-200 rounded-lg px-3 py-2 bg-white text-navy-800 focus:outline-none focus:ring-2 focus:ring-accent-500/20"
          >
            <option value="">All Statuses</option>
            <option value="ACTIVE">Active</option>
            <option value="EXPIRED">Expired</option>
          </select>
          <select
            value={salary_disclosed}
            onChange={(e) => updateFilter('salary_disclosed', e.target.value)}
            className="text-sm border border-gray-200 rounded-lg px-3 py-2 bg-white text-navy-800 focus:outline-none focus:ring-2 focus:ring-accent-500/20"
          >
            <option value="">Salary (Any)</option>
            <option value="true">Disclosed</option>
            <option value="false">Undisclosed</option>
          </select>
        </div>

        {hasFilters && (
          <div className="flex items-center gap-2 flex-wrap text-sm">
            <span className="text-gray-500 text-xs font-medium">Active filters:</span>
            {keyword && (
              <Badge variant="info" onRemove={() => updateFilter('keyword', '')}>
                Keyword: {keyword}
              </Badge>
            )}
            {status && (
              <Badge variant="info" onRemove={() => updateFilter('status', '')}>
                Status: {status}
              </Badge>
            )}
            {salary_disclosed && (
              <Badge variant="info" onRemove={() => updateFilter('salary_disclosed', '')}>
                Salary: {salary_disclosed === 'true' ? 'Disclosed' : 'Undisclosed'}
              </Badge>
            )}
            <button
              type="button"
              onClick={clearFilters}
              className="text-xs text-accent-600 hover:text-accent-800 font-medium ml-auto cursor-pointer"
            >
              Clear all filters
            </button>
          </div>
        )}
      </div>

      {isLoading ? (
        <TableSkeleton rows={7} />
      ) : error ? (
        <ErrorState message="Failed to load job postings." />
      ) : data?.items?.length === 0 ? (
        <EmptyState title="No jobs found" description="Try broadening your search query or filters." />
      ) : (
        <div className="bg-white rounded-xl shadow-sm border border-gray-200 overflow-hidden">
          <div className="hidden md:block">
            <DataTable
              columns={columns}
              data={data?.items || []}
              keyExtractor={(item) => item.id}
              onRowClick={(row) => navigate(`/jobs/${row.id}`)}
            />
          </div>
          <div className="md:hidden divide-y divide-gray-100">
            {data?.items.map((job) => (
              <div
                key={job.id}
                className="p-4 hover:bg-gray-50/50 cursor-pointer space-y-2"
                onClick={() => navigate(`/jobs/${job.id}`)}
              >
                <div className="font-semibold text-navy-900 text-sm">{job.title_normalized || job.title_raw}</div>
                <div className="flex items-center gap-2 text-xs text-gray-500">
                  <span>{job.primary_category || 'Unclassified'}</span>
                  <span>•</span>
                  <span>{job.city || 'Unspecified'}</span>
                </div>
                <div className="flex items-center justify-between text-xs pt-1">
                  <StatusBadge status={job.status} />
                  <span className="font-medium text-emerald-700">
                    {formatSalaryRange(job.salary_min, job.salary_max, job.salary_currency)}
                  </span>
                </div>
              </div>
            ))}
          </div>

          <div className="p-4 border-t border-gray-100">
            <Pagination
              page={page}
              pages={data?.pages || 1}
              total={data?.total || 0}
              pageSize={data?.page_size || 20}
              onPageChange={(p) => updateFilter('page', String(p))}
            />
          </div>
        </div>
      )}
    </div>
  );
}
