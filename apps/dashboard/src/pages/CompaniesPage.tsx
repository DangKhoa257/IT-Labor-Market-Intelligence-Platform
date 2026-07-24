import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useCompanies } from '../hooks/useApi';
import { PageHeader } from '../components/PageHeader';
import { SearchInput } from '../components/SearchInput';
import { DataTable, type Column } from '../components/DataTable';
import { TableSkeleton } from '../components/LoadingSkeleton';
import { ErrorState } from '../components/ErrorState';
import type { CompanyListItem } from '../types/api';

export function CompaniesPage() {
  const [search, setSearch] = useState('');
  const { data: companies, isLoading, error } = useCompanies();
  const navigate = useNavigate();

  const filteredCompanies =
    companies?.filter((c) => c.name.toLowerCase().includes(search.toLowerCase())) || [];

  const columns: Column<CompanyListItem>[] = [
    {
      key: 'name',
      header: 'Company Name',
      render: (row) => <span className="font-semibold text-navy-900">{row.name}</span>,
    },
    {
      key: 'job_count',
      header: 'Total Job Postings',
      render: (row) => row.job_count.toLocaleString(),
    },
    {
      key: 'active_jobs',
      header: 'Active Postings',
      render: (row) => (
        <span className="font-medium text-emerald-700">{row.active_job_count.toLocaleString()}</span>
      ),
    },
  ];

  return (
    <div className="space-y-6 pb-12">
      <PageHeader
        title="Companies"
        description="Search and inspect tech hiring employers tracked in the intelligence database."
      />

      <div className="bg-white p-4 rounded-xl shadow-sm border border-gray-200">
        <SearchInput
          value={search}
          onChange={setSearch}
          placeholder="Filter companies by name..."
        />
      </div>

      {isLoading ? (
        <TableSkeleton rows={5} />
      ) : error ? (
        <ErrorState message="Failed to load company listing data." />
      ) : (
        <div className="bg-white rounded-xl shadow-sm border border-gray-200 overflow-hidden">
          <DataTable
            columns={columns}
            data={filteredCompanies}
            keyExtractor={(item) => item.id}
            onRowClick={(row) => navigate(`/companies/${row.id}`)}
          />
        </div>
      )}
    </div>
  );
}
