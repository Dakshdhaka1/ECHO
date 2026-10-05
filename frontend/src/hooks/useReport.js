import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect } from 'react'
import { api } from '../services/api'

/**
 * Loads a company report. The API answers 200 with a report, or 202 with the analysis job producing it;
 * in that case the job is polled every 1.5 s and the report is refetched when the job is DONE.
 */
export function useReport(companyId, asOf) {
  const qc = useQueryClient()
  const key = ['report', companyId, asOf || 'latest']
  const report = useQuery({
    queryKey: key,
    queryFn: () => api.getEnvelope(`/companies/${companyId}/report${asOf ? `?asOf=${asOf}` : ''}`),
    enabled: !!companyId,
    staleTime: 60_000,
  })
  const jobId = report.data?.httpStatus === 202 ? report.data.job?.id : null
  const job = useQuery({
    queryKey: ['job', jobId],
    queryFn: () => api.get(`/jobs/${jobId}`),
    enabled: !!jobId,
    refetchInterval: (q) => (['DONE', 'FAILED'].includes(q.state.data?.status) ? false : 1500),
  })
  useEffect(() => {
    if (job.data?.status === 'DONE') {
      qc.invalidateQueries({ queryKey: key })
      qc.invalidateQueries({ queryKey: ['history', companyId] })
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [job.data?.status])

  return {
    isLoading: report.isLoading,
    error: report.error || (job.data?.status === 'FAILED' ? new Error(job.data.error || 'Analysis failed') : null),
    report: report.data?.report || null,
    pending: report.data?.httpStatus === 202 && job.data?.status !== 'FAILED',
    job: job.data || report.data?.job || null,
    refetch: report.refetch,
  }
}
