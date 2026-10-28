// Mirrors fbb/api/schemas.py. Keep the two in sync when the API contract changes.

export interface TeamRef {
  id: number
  name: string
  abbrev: string
  record: string
  standing: number
}

export interface CategoryInfo {
  stat: string
  reverse: boolean
}

export interface LeagueMeta {
  name: string
  scoring_type: string
  is_points: boolean
  categories: CategoryInfo[]
  lineup_slots: string[]
  roster_size: number
  my_team: TeamRef
  teams: TeamRef[]
  stat_window: string
  stat_windows: string[]
  punt_categories: string[]
  loaded_at: string
  chat_enabled: boolean
  model: string
}

export interface CategoryOutlook {
  stat: string
  win_prob: number
  mine_now: number
  theirs_now: number
  mine_final: number
  theirs_final: number
}

export interface StartsDay {
  date: string
  mine_starts: number
  mine_open_slots: number
  mine_benched: string[]
  opp_starts: number
  opp_open_slots: number
  opp_benched: string[]
}

export type CellState = 'starts' | 'bench' | 'out'

export interface ScheduleRow {
  player_id: number
  player: string
  status: string
  cells: (CellState | null)[]
}

export interface Matchup {
  opponent: TeamRef | null
  start_date: string | null
  end_date: string | null
  days_left: number
  categories_total: number
  expected_wins: number
  win_prob: number
  my_starts_left: number
  opp_starts_left: number
  points_margin_sd: number | null
  categories: CategoryOutlook[]
  days: StartsDay[]
  schedule: { days: string[]; rows: ScheduleRow[] }
  lineup: {
    date: string
    games_started: boolean
    start: string[]
    bench: string[]
    ir_candidates: string[]
  }
}

export interface PlayerRow {
  id: number
  name: string
  pro_team: string
  positions: string[]
  lineup_slot: string | null
  status: string
  value: number
  games_left: number
  ros_games: number
  gp: number
  minutes: number
  fpts: number
  stat_window: string
  stats: Record<string, number>
}

export interface Roster {
  team: TeamRef
  stats: string[]
  players: PlayerRow[]
  weakest: { name: string; value: number }[]
}

export interface FreeAgentRow extends PlayerRow {
  matchup_gain: number
  win_prob_after: number
  best_drop: string | null
  low_sample: boolean
}

export interface FreeAgentBoard {
  gain_label: string
  rows: FreeAgentRow[]
}

export interface NewsItem {
  published: string
  headline: string
  story: string
}

export interface PlayerDetail extends PlayerRow {
  owner: string | null
  is_mine: boolean
  expected_return: string | null
  windows: Record<string, Record<string, number>>
  upcoming_games: string[]
  news: NewsItem[]
  news_error: string | null
}

export interface TeamRoster {
  team: TeamRef
  players: string[]
}

export interface MoveResult {
  add: string[]
  drop: string[]
  expected_wins_before: number
  expected_wins_after: number
  win_prob_before: number
  win_prob_after: number
  matchup_gain: number
  games_delta: number
  season_value_delta: number
  category_deltas: Record<string, number>
  projected_delta: Record<string, number>
  notes: string[]
}

export interface TradeResult {
  value_change: number
  ros_games_change: number
  matchup_change: number | null
  per_game_change: Record<string, number>
  z_change: Record<string, number>
  roster_overflow: number
}

export interface Standing extends TeamRef {
  points_for: number
  is_me: boolean
}

export interface Activity {
  date: string
  team: string
  action: string
  player: string
}

export type Position = 'PG' | 'SG' | 'SF' | 'PF' | 'C' | 'G' | 'F'

export type AssistantEvent =
  | { event: 'tool'; data: { name: string; label: string } }
  | { event: 'answer'; data: { text: string } }
  | { event: 'error'; data: { message: string } }
