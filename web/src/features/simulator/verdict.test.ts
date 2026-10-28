import type { MoveResult } from '../../api/types'
import { moveVerdict } from './verdict'

const base: MoveResult = {
  add: ['A'],
  drop: ['B'],
  expected_wins_before: 1,
  expected_wins_after: 1,
  win_prob_before: 0.999,
  win_prob_after: 0.999,
  matchup_gain: 0,
  games_delta: 0,
  season_value_delta: 0,
  category_deltas: {},
  projected_delta: {},
  notes: [],
}

describe('moveVerdict', () => {
  it('judges points leagues by projected fantasy points, not near-certain win odds', () => {
    expect(moveVerdict({ ...base, projected_delta: { FPTS: 42 } }, true).title).toContain('Worth it')
    expect(moveVerdict({ ...base, projected_delta: { FPTS: -25 } }, true).title).toContain('Hurts')
    expect(moveVerdict({ ...base, projected_delta: { FPTS: 3 } }, true).title).toContain('wash')
  })

  it('judges category leagues by expected categories', () => {
    expect(moveVerdict({ ...base, matchup_gain: 0.3 }, false).title).toContain('Worth it')
    expect(moveVerdict({ ...base, matchup_gain: -0.3 }, false).title).toContain('Hurts')
  })
})
