import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useSettings } from '../state/useSettings'
import { api } from './endpoints'
import type { Position } from './types'

/** Every league query is keyed by the snapshot settings, so changing them refetches everything. */
function useSnapshotKey() {
  const { params } = useSettings()
  return { params, key: ['league', params.window, params.punts?.join(',') ?? null] as const }
}

export function useMeta() {
  const { params, key } = useSnapshotKey()
  return useQuery({ queryKey: [...key, 'meta'], queryFn: ({ signal }) => api.meta(params, signal) })
}

export function useMatchup() {
  const { params, key } = useSnapshotKey()
  return useQuery({ queryKey: [...key, 'matchup'], queryFn: ({ signal }) => api.matchup(params, signal) })
}

export function useRoster() {
  const { params, key } = useSnapshotKey()
  return useQuery({ queryKey: [...key, 'roster'], queryFn: ({ signal }) => api.roster(params, signal) })
}

export function useFreeAgents(position: Position | null, includeInjured: boolean) {
  const { params, key } = useSnapshotKey()
  return useQuery({
    queryKey: [...key, 'free-agents', position, includeInjured],
    queryFn: ({ signal }) => api.freeAgents(params, position, includeInjured, signal),
    placeholderData: (prev) => prev,
  })
}

export function useTeamRoster(teamId: number | null) {
  const { params, key } = useSnapshotKey()
  return useQuery({
    queryKey: [...key, 'team-roster', teamId],
    queryFn: ({ signal }) => api.teamRoster(params, teamId!, signal),
    enabled: teamId !== null,
  })
}

export function useStandings() {
  const { params, key } = useSnapshotKey()
  return useQuery({ queryKey: [...key, 'standings'], queryFn: ({ signal }) => api.standings(params, signal) })
}

export function useActivity() {
  const { params, key } = useSnapshotKey()
  return useQuery({ queryKey: [...key, 'activity'], queryFn: ({ signal }) => api.activity(params, signal) })
}

export function useReport() {
  const { params, key } = useSnapshotKey()
  return useQuery({ queryKey: [...key, 'report'], queryFn: ({ signal }) => api.report(params, signal) })
}

export function useSimulate() {
  const { params } = useSettings()
  return useMutation({ mutationFn: ({ add, drop }: { add: string[]; drop: string[] }) => api.simulate(params, add, drop) })
}

export function useEvaluateTrade() {
  const { params } = useSettings()
  return useMutation({
    mutationFn: ({ partnerId, give, get }: { partnerId: number; give: string[]; get: string[] }) =>
      api.evaluateTrade(params, partnerId, give, get),
  })
}

export function useRefresh() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: api.refresh,
    onSuccess: () => client.invalidateQueries({ queryKey: ['league'] }),
  })
}
