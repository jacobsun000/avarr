import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { Loader2, RefreshCw, ExternalLink, FileText, ChevronLeft, ChevronRight, X, Trash2, Star, Eye } from 'lucide-react'

import { API_BASE, buildDownloadUrl, createJob, deleteJob, listJobs, updateJobFlags } from './api'
import type { Job } from './api'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Textarea } from '@/components/ui/textarea'
import { Label } from '@/components/ui/label'
import { Badge } from '@/components/ui/badge'
import { Separator } from '@/components/ui/separator'
import { Carousel, CarouselContent, CarouselItem, CarouselNext, CarouselPrevious } from '@/components/ui/carousel'
import { cn } from '@/lib/utils'

const PLACEHOLDER_THUMBNAIL =
  'data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iMTIwIiBoZWlnaHQ9IjkwIiB2aWV3Qm94PSIwIDAgMTIwIDkwIiB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciPjxyZWN0IHdpZHRoPSIxMjAiIGhlaWdodD0iOTAiIGZpbGw9IiMxMDIyMzMiIHJ4PSIxMiIvPjxwYXRoIGQ9Ik0xMCA3NWwzNS0zNSA0NSAxNSA0NS00NSAyMCA1MCIgc3Ryb2tlPSIjMTkzMDQ3IiBzdHJva2Utd2lkdGg9IjQiIGZpbGw9Im5vbmUiIHN0cm9rZS1saW5lY2FwPSJyb3VuZCIvPjxyZWN0IHg9IjMwIiB5PSIyMCIgd2lkdGg9IjYwIiBoZWlnaHQ9IjI2IiByeD0iNiIgZmlsbD0iIzE2MjkzNSIvPjwvc3ZnPg=='

const statusToVariant: Record<Job['status'], Parameters<typeof Badge>[0]['variant']> = {
  pending: 'warning',
  running: 'info',
  completed: 'success',
  failed: 'destructive',
}

type DescriptionState = {
  path: string
  content: string | null
  loading: boolean
  error: string | null
}

const IMAGE_NAME_REGEX = /\.(jpe?g|png|webp|gif|avif|bmp|svg)$/i
const VIDEO_NAME_REGEX = /\.(mp4|mkv|webm|mov|m4v|avi|ts|m2ts|flv|ogg|m3u8)$/i
type MobileView = 'queue' | 'jobs' | 'details'

const formatRelativeShort = (isoDate: string): string => {
  const timestamp = new Date(isoDate).getTime()
  if (!Number.isFinite(timestamp)) {
    return '—'
  }
  const diffSecondsRaw = Math.round((Date.now() - timestamp) / 1000)
  const past = diffSecondsRaw >= 0
  const diffSeconds = Math.max(1, Math.abs(diffSecondsRaw))
  let value: number
  let unit: string
  if (diffSeconds < 60) {
    value = diffSeconds
    unit = 's'
  } else if (diffSeconds < 3600) {
    value = Math.floor(diffSeconds / 60)
    unit = 'm'
  } else if (diffSeconds < 86400) {
    value = Math.floor(diffSeconds / 3600)
    unit = 'h'
  } else if (diffSeconds < 604800) {
    value = Math.floor(diffSeconds / 86400)
    unit = 'd'
  } else {
    value = Math.floor(diffSeconds / 604800)
    unit = 'w'
  }
  return past ? `${value}${unit} ago` : `in ${value}${unit}`
}

const formatAbsolute = (isoDate: string): string => {
  const date = new Date(isoDate)
  if (Number.isNaN(date.getTime())) {
    return 'Unknown'
  }
  return date.toLocaleString()
}

const getImageManifest = (job: Job): string[] => {
  const prefix = job.output_dir ? `${job.output_dir.replace(/\/+$/, '')}/` : ''
  const unique = new Set<string>()
  for (const path of job.file_manifest) {
    if (prefix && !path.startsWith(prefix)) {
      continue
    }
    if (!IMAGE_NAME_REGEX.test(path)) {
      continue
    }
    unique.add(path)
  }
  return Array.from(unique).sort((a, b) => a.localeCompare(b))
}

const getVideoManifest = (job: Job): string[] => {
  const prefix = job.output_dir ? `${job.output_dir.replace(/\/+$/, '')}/` : ''
  const unique = new Set<string>()
  for (const path of job.file_manifest) {
    if (prefix && !path.startsWith(prefix)) {
      continue
    }
    if (!VIDEO_NAME_REGEX.test(path)) {
      continue
    }
    unique.add(path)
  }
  return Array.from(unique).sort((a, b) => a.localeCompare(b))
}

const useMediaQuery = (query: string): boolean => {
  const [matches, setMatches] = useState(() => {
    if (typeof window === 'undefined') {
      return false
    }
    return window.matchMedia(query).matches
  })

  useEffect(() => {
    if (typeof window === 'undefined') {
      return () => {
        /* noop */
      }
    }
    const media = window.matchMedia(query)
    const handler = () => setMatches(media.matches)
    handler()
    media.addEventListener('change', handler)
    return () => media.removeEventListener('change', handler)
  }, [query])

  return matches
}

function App() {
  const [jobs, setJobs] = useState<Job[]>([])
  const [selectedJobId, setSelectedJobId] = useState<string | null>(null)
  const [url, setUrl] = useState('')
  const [loading, setLoading] = useState(false)
  const [deletingJobId, setDeletingJobId] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [descriptions, setDescriptions] = useState<Record<string, DescriptionState>>({})
  const [previewIndex, setPreviewIndex] = useState<number | null>(null)
  const [filterWatched, setFilterWatched] = useState<boolean | null>(null)
  const [filterStarred, setFilterStarred] = useState<boolean | null>(null)
  const isMobile = useMediaQuery('(max-width: 768px)')
  const [mobileView, setMobileView] = useState<MobileView>('queue')
  const pageRef = useRef<HTMLDivElement | null>(null)

  const selectedJob = useMemo(
    () => jobs.find((job) => job.id === selectedJobId) ?? jobs[0] ?? null,
    [jobs, selectedJobId],
  )

  useEffect(() => {
    if (!isMobile && mobileView !== 'queue') {
      setMobileView('queue')
    }
  }, [isMobile, mobileView])

  useEffect(() => {
    if (isMobile && mobileView === 'details' && !selectedJob) {
      setMobileView('jobs')
    }
  }, [isMobile, mobileView, selectedJob])

  const refreshJobs = useCallback(async () => {
    try {
      setError(null)
      const next = await listJobs()
      setJobs(next)
    } catch (err) {
      setError((err as Error).message)
    }
  }, [])

  useEffect(() => {
    refreshJobs()
    const interval = setInterval(refreshJobs, 5000)
    return () => clearInterval(interval)
  }, [refreshJobs])

  useEffect(() => {
    jobs.forEach((job) => {
      if (!job.description_path) {
        return
      }
      const cached = descriptions[job.id]
      if (cached && cached.path === job.description_path && (cached.loading || cached.content || cached.error)) {
        return
      }
      setDescriptions((prev) => ({
        ...prev,
        [job.id]: {
          path: job.description_path!,
          content: cached?.content ?? null,
          loading: true,
          error: null,
        },
      }))
        ; (async () => {
          try {
            const response = await fetch(buildDownloadUrl(job.description_path!))
            if (!response.ok) {
              throw new Error(`Failed to load description (${response.status})`)
            }
            const text = await response.text()
            setDescriptions((prev) => ({
              ...prev,
              [job.id]: { path: job.description_path!, content: text, loading: false, error: null },
            }))
          } catch (err) {
            setDescriptions((prev) => ({
              ...prev,
              [job.id]: {
                path: job.description_path!,
                content: prev[job.id]?.content ?? null,
                loading: false,
                error: (err as Error).message,
              },
            }))
          }
        })()
    })
  }, [jobs, descriptions])

  useEffect(() => {
    setPreviewIndex(null)
  }, [selectedJob?.id])

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (!url.trim()) {
      setError('Enter a URL to queue a download')
      return
    }

    // Parse multiple URLs separated by newlines
    const urls = url
      .split('\n')
      .map((line) => line.trim())
      .filter((line) => line.length > 0)

    if (urls.length === 0) {
      setError('Enter at least one valid URL')
      return
    }

    setLoading(true)
    const errors: string[] = []
    let successCount = 0

    try {
      setError(null)

      // Create jobs for all URLs
      for (const urlItem of urls) {
        try {
          await createJob(urlItem, undefined)
          successCount++
        } catch (err) {
          errors.push(`${urlItem}: ${(err as Error).message}`)
        }
      }

      // Clear form if at least one succeeded
      if (successCount > 0) {
        setUrl('')
        await refreshJobs()
      }

      // Show error summary if any failed
      if (errors.length > 0) {
        if (successCount > 0) {
          setError(`${successCount} job(s) queued successfully. Failed:\n${errors.join('\n')}`)
        } else {
          setError(`All jobs failed:\n${errors.join('\n')}`)
        }
      }
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setLoading(false)
    }
  }

  const handleRemoveJob = async (jobId: string) => {
    if (!jobId) {
      return
    }
    try {
      setError(null)
      setDeletingJobId(jobId)
      await deleteJob(jobId)
      setJobs((prev) => {
        const next = prev.filter((job) => job.id !== jobId)
        if (selectedJobId === jobId) {
          const replacementId = next[0]?.id ?? null
          setSelectedJobId(replacementId)
          setPreviewIndex(null)
        }
        return next
      })
      setDescriptions((prev) => {
        if (!(jobId in prev)) {
          return prev
        }
        const next = { ...prev }
        delete next[jobId]
        return next
      })
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setDeletingJobId(null)
    }
  }

  const handleToggleWatched = async (jobId: string, event: React.MouseEvent) => {
    event.stopPropagation()
    const job = jobs.find((j) => j.id === jobId)
    if (!job) {
      return
    }
    try {
      const updated = await updateJobFlags(jobId, { watched: !job.watched })
      setJobs((prev) => prev.map((j) => (j.id === jobId ? updated : j)))
    } catch (err) {
      setError((err as Error).message)
    }
  }

  const handleToggleStarred = async (jobId: string, event: React.MouseEvent) => {
    event.stopPropagation()
    const job = jobs.find((j) => j.id === jobId)
    if (!job) {
      return
    }
    try {
      const updated = await updateJobFlags(jobId, { starred: !job.starred })
      setJobs((prev) => prev.map((j) => (j.id === jobId ? updated : j)))
    } catch (err) {
      setError((err as Error).message)
    }
  }

  const filteredJobs = useMemo(() => {
    return jobs.filter((job) => {
      if (filterWatched !== null && job.watched !== filterWatched) {
        return false
      }
      if (filterStarred !== null && job.starred !== filterStarred) {
        return false
      }
      return true
    })
  }, [jobs, filterWatched, filterStarred])

  const descriptionState = selectedJob ? descriptions[selectedJob.id] : undefined
  const thumbnails = useMemo(() => (selectedJob ? getImageManifest(selectedJob) : []), [selectedJob])
  const videos = useMemo(() => (selectedJob ? getVideoManifest(selectedJob) : []), [selectedJob])
  const thumbnailUrls = thumbnails.map((path) => ({ path, url: buildDownloadUrl(path) }))
  const videoSources = videos.map((path) => ({ path, url: buildDownloadUrl(path) }))
  const currentPreview = previewIndex !== null ? thumbnailUrls[previewIndex] : null
  const removalBlocked = selectedJob ? selectedJob.status === 'pending' || selectedJob.status === 'running' : true
  const removalDisabled = !selectedJob || removalBlocked || deletingJobId === selectedJob.id
  const removalTooltip = !selectedJob
    ? undefined
    : removalBlocked
      ? 'Only completed or failed jobs can be removed'
      : undefined
  const mobileTabs: { id: MobileView; label: string }[] = [
    { id: 'queue', label: 'Queue' },
    { id: 'jobs', label: `Jobs (${filteredJobs.length})` },
    { id: 'details', label: selectedJob ? 'Details' : 'Details (pick job)' },
  ]

  const handleOpenPreview = (index: number) => {
    setPreviewIndex(index)
  }

  const handleClosePreview = () => setPreviewIndex(null)

  const handleNavigatePreview = useCallback(
    (direction: 'prev' | 'next') => {
      if (previewIndex === null || thumbnailUrls.length === 0) {
        return
      }
      setPreviewIndex((prev) => {
        if (prev === null) {
          return prev
        }
        const delta = direction === 'next' ? 1 : -1
        return (prev + delta + thumbnailUrls.length) % thumbnailUrls.length
      })
    },
    [previewIndex, thumbnailUrls.length],
  )

  useEffect(() => {
    if (previewIndex === null) {
      return
    }
    const handleKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setPreviewIndex(null)
      } else if (event.key === 'ArrowRight') {
        handleNavigatePreview('next')
      } else if (event.key === 'ArrowLeft') {
        handleNavigatePreview('prev')
      }
    }
    window.addEventListener('keydown', handleKey)
    return () => window.removeEventListener('keydown', handleKey)
  }, [previewIndex, handleNavigatePreview])

  return (
    <div className="min-h-screen bg-background text-foreground">
      <div ref={pageRef} className="mx-auto flex w-full flex-col gap-6 px-4 py-8 sm:px-6 lg:px-10">
        <header className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <h1 className="text-3xl font-semibold tracking-tight">Repository Download Control</h1>
            <p className="text-sm text-muted-foreground">Backend: {API_BASE}</p>
          </div>
          <div className="flex items-center gap-3">
            <Button variant="outline" onClick={refreshJobs} disabled={loading} className="gap-2">
              <RefreshCw className={cn('h-4 w-4', loading && 'animate-spin')} /> Refresh
            </Button>
          </div>
        </header>

        {isMobile && (
          <div className="sticky top-0 z-20 -mx-4 flex gap-2 overflow-x-auto rounded-2xl bg-card/90 px-4 py-2 shadow sm:hidden">
            {mobileTabs.map((tab) => {
              const disabled = tab.id === 'details' && !selectedJob
              return (
                <button
                  key={tab.id}
                  type="button"
                  className={cn(
                    'flex-1 rounded-xl px-3 py-2 text-sm font-semibold tracking-tight transition',
                    mobileView === tab.id
                      ? 'bg-primary text-primary-foreground shadow'
                      : 'bg-muted/60 text-muted-foreground',
                    disabled && 'opacity-50',
                  )}
                  onClick={() => !disabled && setMobileView(tab.id)}
                  disabled={disabled}
                  aria-pressed={mobileView === tab.id}
                >
                  {tab.label}
                </button>
              )
            })}
          </div>
        )}

        {(!isMobile || mobileView === 'queue') && (
          <Card className="border-border/60 bg-card/90 shadow-2xl">
            <CardHeader className="pb-4">
              <CardTitle>Queue a Download</CardTitle>
              <CardDescription>Enter one or more URLs (one per line) to queue downloads.</CardDescription>
            </CardHeader>
            <CardContent>
              <form onSubmit={handleSubmit} className="grid gap-4 md:grid-cols-[2fr,1fr,auto]">
                <div className="space-y-2">
                  <Label htmlFor="url">Video URL(s)</Label>
                  <Textarea
                    id="url"
                    placeholder="https://example.com/video&#10;https://example.com/another-video&#10;(one URL per line)"
                    value={url}
                    onChange={(event) => setUrl(event.target.value)}
                    required
                    rows={3}
                    className="resize-y"
                  />
                </div>
                <div className="flex items-end">
                  <Button type="submit" disabled={loading} className="w-full">
                    {loading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />} Queue Download(s)
                  </Button>
                </div>
              </form>
              {error && <p className="mt-3 whitespace-pre-wrap text-sm text-destructive">{error}</p>}
            </CardContent>
          </Card>
        )}

        {(!isMobile || mobileView !== 'queue') && (
          <div className="grid gap-6 lg:grid-cols-2 lg:items-start">
            {(!isMobile || mobileView === 'jobs') && (
              <Card className="border-border/60 bg-card/85 lg:flex lg:h-[calc(100vh-16rem)] lg:flex-col">
                <CardHeader className="pb-4 lg:flex-shrink-0">
                  <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                    <div>
                      <CardTitle>Jobs</CardTitle>
                      <CardDescription>{filteredJobs.length} of {jobs.length} tracked</CardDescription>
                    </div>
                    <div className="flex flex-wrap gap-2">
                      <Button
                        variant={filterStarred === true ? 'default' : 'outline'}
                        size="sm"
                        onClick={() => setFilterStarred(filterStarred === true ? null : true)}
                        className="gap-1.5"
                      >
                        <Star className={cn('h-3.5 w-3.5', filterStarred === true && 'fill-current')} />
                        Starred
                      </Button>
                      <Button
                        variant={filterWatched === true ? 'default' : 'outline'}
                        size="sm"
                        onClick={() => setFilterWatched(filterWatched === true ? null : true)}
                        className="gap-1.5"
                      >
                        <Eye className="h-3.5 w-3.5" />
                        Watched
                      </Button>
                      {(filterStarred !== null || filterWatched !== null) && (
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => {
                            setFilterStarred(null)
                            setFilterWatched(null)
                          }}
                          className="gap-1.5"
                        >
                          <X className="h-3.5 w-3.5" />
                          Clear
                        </Button>
                      )}
                    </div>
                  </div>
                </CardHeader>
                <CardContent className="space-y-3 lg:flex-1 lg:overflow-y-auto">
                  {filteredJobs.length === 0 && jobs.length > 0 && <p className="text-sm text-muted-foreground">No jobs match the current filters.</p>}
                  {jobs.length === 0 && <p className="text-sm text-muted-foreground">No jobs queued yet.</p>}
                  {filteredJobs.map((job) => {
                    const imagePaths = getImageManifest(job)
                    const preview = imagePaths[0] ? buildDownloadUrl(imagePaths[0]) : PLACEHOLDER_THUMBNAIL
                    const isActive = selectedJob?.id === job.id
                    return (
                      <button
                        type="button"
                        key={job.id}
                        onClick={() => {
                          setSelectedJobId(job.id)
                          if (isMobile) {
                            setMobileView('details')
                            pageRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })
                          }
                        }}
                        className={cn(
                          'group flex w-full flex-col items-stretch gap-3 rounded-2xl border border-border/60 bg-muted/20 p-3 text-left transition hover:border-foreground/30 sm:flex-row sm:items-center sm:gap-4',
                          isActive && 'border-primary/70 bg-muted/40 shadow-lg',
                        )}
                      >
                        <img
                          src={preview}
                          alt={job.title ?? job.source_url}
                          className="h-40 w-full flex-none rounded-xl object-cover sm:h-16 sm:w-20"
                          loading="lazy"
                          onError={(event) => {
                            event.currentTarget.src = PLACEHOLDER_THUMBNAIL
                          }}
                        />
                        <div className="flex min-w-0 flex-1 flex-col gap-2">
                          <div className="flex flex-col gap-1">
                            <p className="line-clamp-2 text-base font-semibold sm:line-clamp-1">
                              {job.title ?? 'Untitled job'}
                            </p>
                            <p className="line-clamp-2 text-xs text-muted-foreground sm:line-clamp-1">
                              {job.source_url}
                            </p>
                          </div>
                          <div className="flex flex-wrap items-center gap-2 text-xs">
                            <Badge variant={statusToVariant[job.status]} className="uppercase tracking-tight">
                              {job.status}
                            </Badge>
                            <span className="text-muted-foreground">{formatRelativeShort(job.created_at)}</span>
                            <div className="ml-auto flex items-center gap-1">
                              <button
                                type="button"
                                onClick={(e) => handleToggleStarred(job.id, e)}
                                className={cn(
                                  'rounded p-1 transition hover:bg-muted',
                                  job.starred ? 'text-yellow-500' : 'text-muted-foreground'
                                )}
                                title={job.starred ? 'Unstar' : 'Star'}
                              >
                                <Star className={cn('h-4 w-4', job.starred && 'fill-current')} />
                              </button>
                              <button
                                type="button"
                                onClick={(e) => handleToggleWatched(job.id, e)}
                                className={cn(
                                  'rounded p-1 transition hover:bg-muted',
                                  job.watched ? 'text-blue-500' : 'text-muted-foreground'
                                )}
                                title={job.watched ? 'Mark as unwatched' : 'Mark as watched'}
                              >
                                <Eye className={cn('h-4 w-4', job.watched && 'fill-current')} />
                              </button>
                            </div>
                          </div>
                        </div>
                      </button>
                    )
                  })}
                </CardContent>
              </Card>
            )}

            {(!isMobile || mobileView === 'details') && (
              <Card className="border-border/60 bg-card/85 lg:flex lg:h-[calc(100vh-16rem)] lg:flex-col">
                <CardHeader className="flex flex-col gap-3 pb-4 sm:flex-row sm:items-center sm:justify-between lg:flex-shrink-0">
                  <div className="min-w-0">
                    <CardTitle>Job Details</CardTitle>
                    {selectedJob && <CardDescription className="break-all">Job ID: {selectedJob.id}</CardDescription>}
                  </div>
                  {selectedJob && (
                    <Button
                      variant="destructive"
                      size="sm"
                      className="gap-2 flex-shrink-0"
                      disabled={removalDisabled}
                      onClick={() => handleRemoveJob(selectedJob.id)}
                      title={removalTooltip}
                    >
                      {deletingJobId === selectedJob.id ? (
                        <Loader2 className="h-4 w-4 animate-spin" />
                      ) : (
                        <Trash2 className="h-4 w-4" />
                      )}
                      Remove Job
                    </Button>
                  )}
                </CardHeader>
                <CardContent className="space-y-5 overflow-x-hidden sm:space-y-6 lg:flex-1 lg:overflow-y-auto">
                  {selectedJob ? (
                    <div className="space-y-5 overflow-x-hidden">
                      <div className="space-y-3 overflow-x-hidden">
                        <div className="flex items-center justify-between">
                          <h3 className="text-base font-semibold">Thumbnails</h3>
                          <span className="text-xs text-muted-foreground">{thumbnailUrls.length} found</span>
                        </div>
                        {thumbnailUrls.length === 0 ? (
                          <p className="text-sm text-muted-foreground">No thumbnails saved yet.</p>
                        ) : (
                          <div className="overflow-x-hidden">
                            <Carousel>
                              <CarouselContent>
                                {/* {thumbnailUrls.slice(0, thumbnailUrls.length - 1).map((thumb, index) => ( */}
                                {thumbnailUrls.map((thumb, index) => (
                                  <CarouselItem key={thumb.path} className="basis-full sm:basis-64">
                                    <button
                                      type="button"
                                      onClick={() => handleOpenPreview(index)}
                                      className="group flex w-full items-center justify-center overflow-hidden rounded-2xl border border-border/50 bg-background"
                                    >
                                      <img
                                        src={thumb.url}
                                        alt={thumb.path}
                                        loading="lazy"
                                        className="max-h-full w-full object-contain transition duration-200 group-hover:scale-[1.02]"
                                        onError={(event) => {
                                          event.currentTarget.src = PLACEHOLDER_THUMBNAIL
                                        }}
                                      />
                                    </button>
                                  </CarouselItem>
                                ))}
                              </CarouselContent>
                              <CarouselPrevious className={thumbnailUrls.length <= 1 ? 'lg:hidden' : undefined} />
                              <CarouselNext className={thumbnailUrls.length <= 1 ? 'lg:hidden' : undefined} />
                            </Carousel>
                          </div>
                        )}
                      </div>

                      <Separator className="border-border/50" />

                      <div className="space-y-3 overflow-x-hidden">
                        <div className="flex items-center justify-between">
                          <h3 className="text-base font-semibold">Videos</h3>
                          <span className="text-xs text-muted-foreground">{videoSources.length} streamable files</span>
                        </div>
                        {videoSources.length === 0 ? (
                          <p className="text-sm text-muted-foreground">No video files available yet.</p>
                        ) : (
                          <div className="space-y-4 overflow-x-hidden">
                            {videoSources.map((video) => (
                              <div key={video.path} className="space-y-2 overflow-hidden rounded-2xl border border-border/50 bg-muted/10 p-4">
                                <video
                                  controls
                                  preload="metadata"
                                  className="max-w-full rounded-xl bg-black"
                                  src={video.url}
                                  controlsList="nodownload"
                                >
                                  <track kind="captions" />
                                </video>
                                <div className="flex flex-col gap-2 text-xs text-muted-foreground sm:flex-row sm:items-center sm:justify-between sm:gap-3">
                                  <span className="min-w-0 break-all">{video.path}</span>
                                  <a
                                    href={video.url}
                                    target="_blank"
                                    rel="noreferrer"
                                    className="flex flex-shrink-0 items-center gap-1 font-medium text-primary hover:underline"
                                  >
                                    <ExternalLink className="h-3 w-3" />
                                    Open file
                                  </a>
                                </div>
                              </div>
                            ))}
                          </div>
                        )}
                      </div>

                      <Separator className="border-border/50" />

                      <div className="space-y-3 overflow-hidden rounded-2xl border border-border/50 bg-muted/20 p-4">
                        <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between sm:gap-4">
                          <div className="min-w-0 overflow-hidden">
                            <p className="text-sm text-muted-foreground">Title</p>
                            <p className="break-words text-lg font-semibold">
                              {selectedJob.title ?? 'Untitled job'}
                            </p>
                          </div>
                          <Badge variant={statusToVariant[selectedJob.status]} className="self-start sm:self-auto">{selectedJob.status}</Badge>
                        </div>
                        <div className="space-y-2 overflow-hidden text-sm text-foreground/80">
                          <div className="flex items-start gap-2 overflow-hidden">
                            <ExternalLink className="mt-0.5 h-4 w-4 flex-shrink-0 text-muted-foreground" />
                            <a
                              href={selectedJob.source_url}
                              target="_blank"
                              rel="noreferrer"
                              className="min-w-0 flex-1 break-all text-primary hover:underline"
                            >
                              {selectedJob.source_url}
                            </a>
                          </div>
                          <div className="flex items-center gap-2">
                            <FileText className="h-4 w-4 flex-shrink-0 text-muted-foreground" />
                            <span>Progress: {selectedJob.progress.toFixed(1)}%</span>
                          </div>
                          <div className="flex flex-wrap items-center gap-2 overflow-hidden">
                            <span className="text-muted-foreground">Created:</span>
                            <span className="break-all">{formatAbsolute(selectedJob.created_at)}</span>
                          </div>
                          <div className="flex items-center gap-2 text-xs uppercase tracking-wide text-muted-foreground">
                            Updated {formatRelativeShort(selectedJob.updated_at)}
                          </div>
                          {selectedJob.error && (
                            <p className="break-words text-sm text-destructive">{selectedJob.error}</p>
                          )}
                          {selectedJob.output_dir && (
                            <div className="overflow-hidden text-xs text-muted-foreground">
                              <span>Folder:</span>
                              <code className="ml-2 block break-all rounded bg-card px-2 py-0.5 text-xs text-foreground">
                                /downloads/{selectedJob.output_dir}
                              </code>
                            </div>
                          )}
                        </div>
                      </div>

                      <Separator className="border-border/50" />

                      <div className="space-y-3 overflow-x-hidden">
                        <div className="flex items-center gap-2">
                          <h3 className="text-base font-semibold">Description</h3>
                        </div>
                        {!selectedJob.description_path && (
                          <p className="text-sm text-muted-foreground">No description provided by the source.</p>
                        )}
                        {selectedJob.description_path && (
                          <div className="overflow-hidden rounded-2xl border border-border/50 bg-muted/10 p-4 text-sm leading-relaxed">
                            {descriptionState?.loading && <p className="text-muted-foreground">Loading description...</p>}
                            {descriptionState?.error && (
                              <p className="text-destructive">Failed to load description: {descriptionState.error}</p>
                            )}
                            {!descriptionState?.loading && !descriptionState?.error && (
                              <p className="whitespace-pre-wrap break-words overflow-wrap-anywhere">{descriptionState?.content ?? 'No description content.'}</p>
                            )}
                          </div>
                        )}
                      </div>

                      <Separator className="border-border/50" />

                      <div className="space-y-3 overflow-x-hidden">
                        <div className="flex items-center justify-between">
                          <h3 className="text-base font-semibold">Files</h3>
                          <span className="text-xs text-muted-foreground">{selectedJob.file_manifest.length} items</span>
                        </div>
                        <div className="max-h-48 space-y-2 overflow-y-auto overflow-x-hidden rounded-2xl border border-border/50 bg-muted/10 p-3 text-sm">
                          {selectedJob.file_manifest.length === 0 && (
                            <p className="text-muted-foreground">No files yet</p>
                          )}
                          {selectedJob.file_manifest.map((path) => (
                            <a
                              key={path}
                              href={buildDownloadUrl(path)}
                              target="_blank"
                              rel="noreferrer"
                              className="block break-all text-primary hover:text-primary/80"
                            >
                              {path}
                            </a>
                          ))}
                        </div>
                      </div>
                    </div>
                  ) : (
                    <p className="text-sm text-muted-foreground">Select a job to see the details.</p>
                  )}
                </CardContent>
              </Card>
            )}
          </div>
        )}
      </div>
      {currentPreview && (
        <div className="fixed inset-0 z-50 flex flex-col bg-black/80 backdrop-blur">
          <div className="flex items-center justify-between border-b border-white/10 px-6 py-4 text-white">
            <div className="min-w-0">
              <p className="text-xs uppercase tracking-wide text-white/60">Preview</p>
              <p className="truncate text-lg font-semibold">
                {selectedJob?.title ?? selectedJob?.source_url ?? 'Preview'}
              </p>
            </div>
            <div className="flex items-center gap-2">
              <Button
                variant="secondary"
                size="icon"
                disabled={thumbnailUrls.length <= 1}
                onClick={() => handleNavigatePreview('prev')}
                className="bg-white/15 text-white hover:bg-white/25 disabled:opacity-40"
              >
                <ChevronLeft className="h-4 w-4" />
              </Button>
              <Button
                variant="secondary"
                size="icon"
                disabled={thumbnailUrls.length <= 1}
                onClick={() => handleNavigatePreview('next')}
                className="bg-white/15 text-white hover:bg-white/25 disabled:opacity-40"
              >
                <ChevronRight className="h-4 w-4" />
              </Button>
              <Button
                variant="secondary"
                onClick={handleClosePreview}
                className="bg-white/15 px-3 text-white hover:bg-white/25"
              >
                <X className="mr-2 h-4 w-4" /> Close
              </Button>
            </div>
          </div>
          <div className="flex-1 overflow-auto px-6 py-6">
            <div className="flex min-h-full items-center justify-center">
              <img
                src={currentPreview.url}
                alt={currentPreview.path}
                className="max-h-[80vh] w-full object-contain"
              />
            </div>
          </div>
          <div className="flex gap-3 overflow-x-auto border-t border-white/10 bg-black/40 px-6 py-4">
            {thumbnailUrls.map((thumb, index) => (
              <button
                type="button"
                key={thumb.path}
                onClick={() => setPreviewIndex(index)}
                className={cn(
                  'flex h-20 w-32 items-center justify-center rounded-xl border border-white/20 bg-black/30 p-1',
                  index === previewIndex && 'ring-2 ring-white',
                )}
              >
                <img
                  src={thumb.url}
                  alt={thumb.path}
                  className="max-h-full w-full object-contain"
                  onError={(event) => {
                    event.currentTarget.src = PLACEHOLDER_THUMBNAIL
                  }}
                />
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

export default App
