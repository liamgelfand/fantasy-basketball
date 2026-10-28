import type { MoveResult } from '../../api/types'
import { pct, signed } from '../../lib/format'

/**
 * Judge a move by what it adds to this matchup. Points leagues use projected fantasy points:
 * win odds often sit near 0% or 100% there, which would make every move look like a wash.
 */
export function moveVerdict(res: MoveResult, isPoints: boolean): { title: string; reason: string } {
  const winDelta = res.win_prob_after - res.win_prob_before
  if (isPoints) {
    const fpts = res.projected_delta.FPTS ?? 0
    const reason = `${signed(fpts, 0)} projected fantasy points this matchup, win odds ${pct(res.win_prob_before)} → ${pct(res.win_prob_after)}`
    if (fpts >= 10) return { title: '✅ Worth it', reason }
    if (fpts <= -10) return { title: '🚫 Hurts you', reason }
    return { title: '🤷 Basically a wash', reason }
  }
  const reason = `${signed(res.matchup_gain, 2)} expected categories, win odds ${pct(res.win_prob_before)} → ${pct(res.win_prob_after)}`
  if (res.matchup_gain >= 0.1 || winDelta > 0.02) return { title: '✅ Worth it', reason }
  if (res.matchup_gain <= -0.1 || winDelta < -0.02) return { title: '🚫 Hurts you', reason }
  return { title: '🤷 Basically a wash', reason }
}
