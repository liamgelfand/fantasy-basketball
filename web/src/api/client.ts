import type { AssistantEvent } from './types'

export class ApiError extends Error {
  readonly status: number

  constructor(status: number, message: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

/** Snapshot settings every league request carries; the server caches one snapshot per combination. */
export interface SnapshotParams {
  window: string | null
  punts: string[] | null
}

type Query = Record<string, string | number | boolean | string[] | null | undefined>

export function buildUrl(path: string, query: Query = {}): string {
  const params = new URLSearchParams()
  for (const [key, value] of Object.entries(query)) {
    if (value === null || value === undefined) continue
    for (const v of Array.isArray(value) ? value : [value]) params.append(key, String(v))
  }
  const qs = params.toString()
  return `/api${path}${qs ? `?${qs}` : ''}`
}

export function snapshotQuery({ window, punts }: SnapshotParams): Query {
  // An empty punt list must still be sent, or the server falls back to the .env default.
  return { window, punt: punts === null ? null : punts.length ? punts : [''] }
}

async function errorFrom(res: Response): Promise<ApiError> {
  let message = `${res.status} ${res.statusText}`
  try {
    const body = await res.json()
    if (typeof body.detail === 'string') message = body.detail
    else if (Array.isArray(body.detail)) message = body.detail.map((d: { msg: string }) => d.msg).join('; ')
  } catch {
    /* non-JSON error body: keep the status line */
  }
  return new ApiError(res.status, message)
}

export async function request<T>(method: string, url: string, body?: unknown, signal?: AbortSignal): Promise<T> {
  const res = await fetch(url, {
    method,
    signal,
    headers: body === undefined ? undefined : { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  })
  if (!res.ok) throw await errorFrom(res)
  return (res.status === 204 ? undefined : await res.json()) as T
}

/** Parse a `text/event-stream` body into typed events. Split out so it can be unit tested. */
export function parseSseChunk(buffer: string): { events: AssistantEvent[]; rest: string } {
  const blocks = buffer.split('\n\n')
  const rest = blocks.pop() ?? ''
  const events: AssistantEvent[] = []
  for (const block of blocks) {
    let event = ''
    let data = ''
    for (const line of block.split('\n')) {
      if (line.startsWith('event: ')) event = line.slice(7)
      else if (line.startsWith('data: ')) data += line.slice(6)
    }
    if (event && data) events.push({ event, data: JSON.parse(data) } as AssistantEvent)
  }
  return { events, rest }
}

/** POST and consume a server-sent event stream (EventSource only supports GET). */
export async function streamEvents(
  url: string,
  body: unknown,
  onEvent: (e: AssistantEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const res = await fetch(url, {
    method: 'POST',
    signal,
    headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream' },
    body: JSON.stringify(body ?? {}),
  })
  if (!res.ok || !res.body) throw await errorFrom(res)
  const reader = res.body.pipeThrough(new TextDecoderStream()).getReader()
  let buffer = ''
  for (;;) {
    const { value, done } = await reader.read()
    if (done) break
    const parsed = parseSseChunk(buffer + value.replace(/\r\n/g, '\n'))
    buffer = parsed.rest
    parsed.events.forEach(onEvent)
  }
}
