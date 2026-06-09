import { useEffect, useRef } from 'react'
import { getJob } from '../api'
import type { Job } from '../types'

export function useJobPoller(
  jobId: string | null,
  onComplete: (job: Job) => void,
  onError: (msg: string) => void,
) {
  // Stable refs so we don't re-create the interval when callbacks change.
  const onCompleteRef = useRef(onComplete)
  const onErrorRef    = useRef(onError)
  onCompleteRef.current = onComplete
  onErrorRef.current    = onError

  useEffect(() => {
    if (!jobId) return

    const id = setInterval(async () => {
      try {
        const job = await getJob(jobId)
        if (job.status === 'complete') {
          clearInterval(id)
          onCompleteRef.current(job)
        } else if (job.status === 'failed') {
          clearInterval(id)
          onErrorRef.current(job.error ?? 'Analysis failed')
        }
      } catch {
        // network hiccup — keep polling
      }
    }, 3_000)

    return () => clearInterval(id)
  }, [jobId])
}
