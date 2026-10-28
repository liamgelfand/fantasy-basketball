import { buildUrl, request, snapshotQuery, streamEvents, type SnapshotParams } from './client'
import type {
  Activity,
  AssistantEvent,
  FreeAgentBoard,
  LeagueMeta,
  Matchup,
  MoveResult,
  Position,
  Roster,
  Standing,
  TeamRoster,
  TradeResult,
} from './types'

const get = <T>(path: string, s: SnapshotParams, extra = {}, signal?: AbortSignal) =>
  request<T>('GET', buildUrl(path, { ...snapshotQuery(s), ...extra }), undefined, signal)

const post = <T>(path: string, s: SnapshotParams, body?: unknown) =>
  request<T>('POST', buildUrl(path, snapshotQuery(s)), body)

export const api = {
  meta: (s: SnapshotParams, signal?: AbortSignal) => get<LeagueMeta>('/meta', s, {}, signal),
  matchup: (s: SnapshotParams, signal?: AbortSignal) => get<Matchup>('/matchup', s, {}, signal),
  roster: (s: SnapshotParams, signal?: AbortSignal) => get<Roster>('/roster', s, {}, signal),
  freeAgents: (s: SnapshotParams, position: Position | null, includeInjured: boolean, signal?: AbortSignal) =>
    get<FreeAgentBoard>('/free-agents', s, { position, include_injured: includeInjured }, signal),
  teamRoster: (s: SnapshotParams, teamId: number, signal?: AbortSignal) =>
    get<TeamRoster>(`/teams/${teamId}/roster`, s, {}, signal),
  standings: (s: SnapshotParams, signal?: AbortSignal) => get<Standing[]>('/standings', s, {}, signal),
  activity: (s: SnapshotParams, signal?: AbortSignal) => get<Activity[]>('/activity', s, { limit: 30 }, signal),
  report: (s: SnapshotParams, signal?: AbortSignal) => get<{ markdown: string }>('/report', s, {}, signal),

  simulate: (s: SnapshotParams, add: string[], drop: string[]) => post<MoveResult>('/simulate', s, { add, drop }),
  evaluateTrade: (s: SnapshotParams, partnerId: number, give: string[], getPlayers: string[]) =>
    post<TradeResult>('/trades/evaluate', s, { partner_id: partnerId, give, get: getPlayers }),
  refresh: () => request<void>('POST', buildUrl('/refresh')),

  createChat: (s: SnapshotParams) => post<{ id: string }>('/assistant/sessions', s),
  deleteChat: (id: string) => request<void>('DELETE', buildUrl(`/assistant/sessions/${id}`)),
  sendChat: (id: string, text: string, onEvent: (e: AssistantEvent) => void, signal?: AbortSignal) =>
    streamEvents(buildUrl(`/assistant/sessions/${id}/messages`), { text }, onEvent, signal),
  gamePlan: (s: SnapshotParams, onEvent: (e: AssistantEvent) => void, signal?: AbortSignal) =>
    streamEvents(buildUrl('/assistant/game-plan', snapshotQuery(s)), {}, onEvent, signal),
}
