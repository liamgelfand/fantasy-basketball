import { fireEvent, screen } from '@testing-library/react'
import { renderWithTheme } from '../../test/render'
import { ChatComposer } from './ChatComposer'

describe('ChatComposer', () => {
  it('sends on Enter, keeps Shift+Enter for new lines, and clears the box', () => {
    const onSend = vi.fn()
    renderWithTheme(<ChatComposer onSend={onSend} onStop={() => {}} busy={false} disabled={false} />)
    const box = screen.getByLabelText('Message Claude')

    fireEvent.change(box, { target: { value: 'who do I drop?' } })
    fireEvent.keyDown(box, { key: 'Enter', shiftKey: true })
    expect(onSend).not.toHaveBeenCalled()

    fireEvent.keyDown(box, { key: 'Enter' })
    expect(onSend).toHaveBeenCalledWith('who do I drop?')
    expect(box).toHaveValue('')
  })

  it('shows a stop button while Claude is answering', () => {
    const onStop = vi.fn()
    renderWithTheme(<ChatComposer onSend={() => {}} onStop={onStop} busy disabled={false} />)
    fireEvent.click(screen.getByLabelText('Stop'))
    expect(onStop).toHaveBeenCalled()
  })
})
