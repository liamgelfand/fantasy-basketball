import { MultiSelect, Select, Stack } from '@mantine/core'
import type { LeagueMeta } from '../api/types'
import { useSettings } from '../state/useSettings'

const WINDOW_LABELS: Record<string, string> = {
  blend: 'Blend (season + projection)',
  season: 'Season',
  last_30: 'Last 30 days',
  last_15: 'Last 15 days',
  last_7: 'Last 7 days',
  projected: 'ESPN projection',
}

export function SettingsPanel({ meta }: { meta: LeagueMeta }) {
  const { setWindow, setPunts } = useSettings()
  return (
    <Stack gap="sm">
      <Select
        label="Stat window"
        description="Which stats drive values and projections"
        data={meta.stat_windows.map((w) => ({ value: w, label: WINDOW_LABELS[w] ?? w }))}
        value={meta.stat_window}
        onChange={(w) => w && setWindow(w)}
        allowDeselect={false}
      />
      {!meta.is_points && (
        <MultiSelect
          label="Punt categories"
          description="Ignored when valuing players"
          placeholder={meta.punt_categories.length ? undefined : 'None'}
          data={meta.categories.map((c) => c.stat)}
          value={meta.punt_categories}
          onChange={setPunts}
          clearable
        />
      )}
    </Stack>
  )
}
