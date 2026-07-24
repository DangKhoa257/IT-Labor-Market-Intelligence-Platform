import { useState } from 'react';
import { useSkills } from '../hooks/useApi';
import { PageHeader } from '../components/PageHeader';
import { SearchInput } from '../components/SearchInput';
import { DataTable } from '../components/DataTable';
import { Badge } from '../components/Badge';
import { TableSkeleton } from '../components/LoadingSkeleton';
import type { SkillItem } from '../types/api';

export function SkillsPage() {
  const [search, setSearch] = useState('');
  const { data: skills, isLoading } = useSkills();

  const filteredSkills = skills?.filter((skill: SkillItem) => 
    skill.canonical_name.toLowerCase().includes(search.toLowerCase())
  ) || [];

  const columns = [
    { key: 'rank', header: 'Rank', render: (_: SkillItem, idx: number) => idx + 1 },
    { key: 'name', header: 'Skill Name', render: (row: SkillItem) => <span className="font-medium text-gray-900">{row.canonical_name}</span> },
    { key: 'category', header: 'Category', render: (row: SkillItem) => <Badge variant="primary">{row.category || 'General'}</Badge> },
    { key: 'job_count', header: 'Job Count', render: (row: SkillItem) => row.job_count.toLocaleString() },
    { key: 'companies', header: 'Companies', render: (row: SkillItem) => row.companies?.length?.toLocaleString() || '-' },
  ];

  return (
    <div className="space-y-6 pb-12">
      <PageHeader 
        title="Skills" 
        description="Ranking of most demanded skills across all job postings." 
      />

      <div className="bg-white p-4 rounded-lg shadow-sm border border-gray-200">
        <SearchInput 
          value={search}
          onChange={setSearch}
          placeholder="Filter skills by name..."
        />
      </div>

      {isLoading ? (
        <TableSkeleton rows={5} />
      ) : (
        <div className="bg-white rounded-lg shadow-sm border border-gray-200 overflow-hidden">
          <DataTable 
            columns={columns} 
            data={filteredSkills} 
            keyExtractor={(item: SkillItem) => item.canonical_name}
          />
        </div>
      )}
    </div>
  );
}
