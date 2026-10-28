import { createTheme, type MantineColorsTuple } from '@mantine/core'

// Basketball orange, tuned so the 6th shade passes contrast on white.
const court: MantineColorsTuple = [
  '#fff4e6', '#ffe8cc', '#ffd8a8', '#ffc078', '#ffa94d',
  '#ff922b', '#f76707', '#e8590c', '#d9480f', '#bf400d',
]

export const ME_COLOR = 'indigo.6'
export const OPP_COLOR = 'court.6'

export const theme = createTheme({
  primaryColor: 'court',
  primaryShade: { light: 6, dark: 5 },
  colors: { court },
  fontFamily: 'Inter, system-ui, -apple-system, "Segoe UI", sans-serif',
  headings: { fontFamily: 'Outfit, Inter, system-ui, sans-serif', fontWeight: '700' },
  defaultRadius: 'md',
  cursorType: 'pointer',
  components: {
    Paper: { defaultProps: { withBorder: true, radius: 'lg', p: 'lg' } },
    Card: { defaultProps: { withBorder: true, radius: 'lg' } },
    Badge: { defaultProps: { radius: 'sm' } },
    Tooltip: { defaultProps: { withArrow: true } },
  },
})
