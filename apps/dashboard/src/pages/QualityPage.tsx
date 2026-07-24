import { useQualitySummary } from '../hooks/useApi';
import { PageHeader } from '../components/PageHeader';
import { StatCard } from '../components/StatCard';
import { CardSkeleton } from '../components/LoadingSkeleton';
import { DataTable, type Column } from '../components/DataTable';
import { Badge } from '../components/Badge';
import { ErrorState } from '../components/ErrorState';
import { ShieldCheck } from 'lucide-react';

type IssueItem = {
  code: string;
  severity: 'INFO' | 'WARNING' | 'ERROR' | 'REJECT';
  count: number;
};

export function QualityPage() {
  const { data: quality, isLoading, error } = useQualitySummary();

  const getSeverity = (severity: IssueItem['severity']): 'danger' | 'warning' | 'info' => {
    if (severity === 'ERROR' || severity === 'REJECT') return 'danger';
    if (severity === 'WARNING') return 'warning';
    return 'info';
  };

  const columns: Column<IssueItem>[] = [
    {
      key: 'code',
      header: 'Issue Code',
      render: (row) => (
        <code className="text-xs bg-gray-100 text-gray-800 px-2 py-1 rounded font-mono">{row.code}</code>
      ),
    },
    {
      key: 'count',
      header: 'Occurrences',
      render: (row) => row.count.toLocaleString(),
    },
    {
      key: 'severity',
      header: 'Severity',
      render: (row) => (
        <Badge variant={getSeverity(row.severity)}>
          {row.severity}
        </Badge>
      ),
    },
  ];

  if (error) {
    return <ErrorState message="Failed to load quality data." />;
  }

  const evaluatedRecords = quality ? quality.accepted_records + quality.rejected_records : 0;
  const passRate = quality && evaluatedRecords > 0 
    ? (quality.accepted_records / evaluatedRecords) * 100
    : 100;

  return (
    <div className="space-y-6 pb-12">
      <PageHeader 
        title="Data Quality" 
        description="Monitoring validation findings and pipeline rules across ingested job postings." 
      />

      {isLoading ? (
        <CardSkeleton />
      ) : quality ? (
        <>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            <StatCard label="Total Validated Jobs" value={quality.total_jobs.toLocaleString()} icon={ShieldCheck} />
            <StatCard label="Accepted Records" value={quality.accepted_records.toLocaleString()} />
            <StatCard label="Rejected Records" value={quality.rejected_records.toLocaleString()} />
            <StatCard label="Records with INFO Notices" value={quality.records_with_info_notices.toLocaleString()} />
            <StatCard label="Records with WARNING/ERROR" value={quality.records_with_warning_or_error_issues.toLocaleString()} />
            <StatCard label="Title Classification Coverage" value={`${(quality.title_classification_coverage * 100).toFixed(1)}%`} />
          </div>

          {quality.issues.length === 0 ? (
            <div className="bg-emerald-50 border border-emerald-200 text-emerald-800 p-4 rounded-xl flex items-center shadow-sm text-sm">
              <ShieldCheck className="w-5 h-5 mr-2 text-emerald-600 shrink-0" />
              <span className="font-semibold">All ingested records passed validation without severity issues.</span>
            </div>
          ) : (
            <div className="space-y-6">
              <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
                <h3 className="text-sm font-semibold text-navy-800 mb-2">Record Acceptance Rate</h3>
                <div className="w-full bg-gray-100 rounded-full h-3 mb-2">
                  <div
                    className="bg-emerald-600 h-3 rounded-full transition-all duration-500"
                    style={{ width: `${passRate}%` }}
                  ></div>
                </div>
                <p className="text-xs text-gray-500 text-right font-mono">{passRate.toFixed(1)}% accepted</p>
              </div>

              <div className="bg-white rounded-xl shadow-sm border border-gray-200 overflow-hidden">
                <div className="px-5 py-3 border-b border-gray-100 bg-gray-50">
                  <h3 className="text-sm font-semibold text-navy-800">Identified Validation Codes</h3>
                </div>
                <DataTable 
                  columns={columns} 
                  data={quality.issues} 
                  keyExtractor={(item) => item.code} 
                />
              </div>
            </div>
          )}
        </>
      ) : null}
    </div>
  );
}
