import type { JobFilters } from '../types/api';

export const queryKeys = {
  health: ['health'] as const,
  jobs: (filters?: JobFilters) => ['jobs', filters ?? {}] as const,
  jobDetail: (id: number) => ['jobs', 'detail', id] as const,
  companies: ['companies'] as const,
  companyDetail: (id: number) => ['companies', 'detail', id] as const,
  skills: ['skills'] as const,
  analyticsOverview: ['analytics', 'overview'] as const,
  analyticsCategories: ['analytics', 'categories'] as const,
  analyticsSkills: ['analytics', 'skills'] as const,
  analyticsSalaries: ['analytics', 'salaries'] as const,
  analyticsLocations: ['analytics', 'locations'] as const,
  qualitySummary: ['quality', 'summary'] as const,
  duplicates: ['duplicates'] as const,
};
