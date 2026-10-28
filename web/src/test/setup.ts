import '@testing-library/jest-dom/vitest'

// jsdom lacks these browser APIs that Mantine relies on.
Object.defineProperty(window, 'matchMedia', {
  writable: true,
  value: (query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => false,
  }),
})

class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
window.ResizeObserver = ResizeObserverStub as unknown as typeof ResizeObserver
Element.prototype.scrollIntoView = () => {}
Element.prototype.scrollTo = () => {}

// jsdom has no FontFaceSet; Textarea autosize listens for font loads.
Object.defineProperty(document, 'fonts', {
  value: { addEventListener: () => {}, removeEventListener: () => {}, ready: Promise.resolve() },
})
