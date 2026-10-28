import {
  IconArrowsExchange,
  IconChartBar,
  IconFileText,
  IconFlask,
  IconMessageChatbot,
  IconShoppingCart,
  IconTrophy,
  IconUsers,
} from '@tabler/icons-react'
import type { ComponentType } from 'react'

export interface NavItem {
  path: string
  label: string
  icon: ComponentType<{ size?: number; stroke?: number }>
  description: string
}

export const NAV: NavItem[] = [
  { path: '/', label: 'Matchup', icon: IconChartBar, description: 'Live projection for this week' },
  { path: '/roster', label: 'Roster', icon: IconUsers, description: 'Your players, ranked' },
  { path: '/free-agents', label: 'Free agents', icon: IconShoppingCart, description: 'Pickups that move the needle' },
  { path: '/simulator', label: 'Simulator', icon: IconFlask, description: 'Test adds and drops' },
  { path: '/trades', label: 'Trades', icon: IconArrowsExchange, description: 'Evaluate a deal' },
  { path: '/league', label: 'League', icon: IconTrophy, description: 'Standings and activity' },
  { path: '/chat', label: 'Ask Claude', icon: IconMessageChatbot, description: 'AI analyst with live data' },
  { path: '/report', label: 'Report', icon: IconFileText, description: 'Full write-up and game plan' },
]
