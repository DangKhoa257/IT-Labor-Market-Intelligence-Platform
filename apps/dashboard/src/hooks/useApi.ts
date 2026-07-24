import { useQuery } from '@tanstack/react-query';
import { api } from '../api/client';
import { queryKeys } from '../api/queryKeys';
import type { JobFilters } from '../types/api';

export function useHealth() {
  return useQuery({
    queryKey: queryKeys.health,
    queryFn: api.health,
    refetchInterval: 30000,
    retry: 1,
  });
}

export function useJobs(filters?: JobFilters) {
  return useQuery({
    queryKey: queryKeys.jobs(filters),
    queryFn: () => api.jobs(filters),
    placeholderData: (prev) => prev, // keepPreviousData equivalent
  });
}

export function useJobDetail(id: number) {
  return useQuery({
    queryKey: queryKeys.jobDetail(id),
    queryFn: () => api.jobDetail(id),
    enabled: id > 0,
  });
}

export function useCompanies() {
  return useQuery({
    queryKey: queryKeys.companies,
    queryFn: api.companies,
  });
}

export function useCompanyDetail(id: number) {
  return useQuery({
    queryKey: queryKeys.companyDetail(id),
    queryFn: () => api.companyDetail(id),
    enabled: id > 0,
  });
}

export function useSkills() {
  return useQuery({
    queryKey: queryKeys.skills,
    queryFn: api.skills,
  });
}

export function useAnalyticsOverview() {
  return useQuery({
    queryKey: queryKeys.analyticsOverview,
    queryFn: api.analyticsOverview,
  });
}

export function useAnalyticsCategories() {
  return useQuery({
    queryKey: queryKeys.analyticsCategories,
    queryFn: api.analyticsCategories,
  });
}

export function useAnalyticsSkills() {
  return useQuery({
    queryKey: queryKeys.analyticsSkills,
    queryFn: api.analyticsSkills,
  });
}

export function useAnalyticsSalaries() {
  return useQuery({
    queryKey: queryKeys.analyticsSalaries,
    queryFn: api.analyticsSalaries,
  });
}

export function useAnalyticsLocations() {
  return useQuery({
    queryKey: queryKeys.analyticsLocations,
    queryFn: api.analyticsLocations,
  });
}

export function useQualitySummary() {
  return useQuery({
    queryKey: queryKeys.qualitySummary,
    queryFn: api.qualitySummary,
  });
}

export function useDuplicates() {
  return useQuery({
    queryKey: queryKeys.duplicates,
    queryFn: api.duplicates,
  });
}
