import { MantineProvider } from '@mantine/core'
import { render } from '@testing-library/react'
import type { ReactElement } from 'react'
import { theme } from '../theme'

export function renderWithTheme(ui: ReactElement) {
  return render(
    <MantineProvider theme={theme} env="test">
      {ui}
    </MantineProvider>,
  )
}
