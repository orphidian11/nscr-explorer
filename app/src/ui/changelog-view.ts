import { RELEASES, type Release } from './changelog'

/** Build (once) and toggle the release-notes modal. */
let modal: HTMLElement | null = null

function buildModal(): HTMLElement {
  const overlay = document.createElement('div')
  overlay.className = 'changelog-overlay'
  overlay.hidden = true

  const dialog = document.createElement('div')
  dialog.className = 'changelog-dialog'

  const header = document.createElement('div')
  header.className = 'changelog-header'
  const h2 = document.createElement('h2')
  h2.textContent = 'Release notes'
  const close = document.createElement('button')
  close.className = 'changelog-close'
  close.type = 'button'
  close.textContent = '×'
  close.title = 'Close'
  close.addEventListener('click', () => {
    overlay.hidden = true
  })
  header.append(h2, close)

  const body = document.createElement('div')
  body.className = 'changelog-body'
  for (const release of RELEASES) {
    body.append(renderRelease(release))
  }

  // Click outside the dialog closes it; Esc too.
  overlay.addEventListener('click', (e) => {
    if (e.target === overlay) overlay.hidden = true
  })
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && !overlay.hidden) overlay.hidden = true
  })

  dialog.append(header, body)
  overlay.append(dialog)
  document.body.appendChild(overlay)
  return overlay
}

function renderRelease(release: Release): HTMLElement {
  const section = document.createElement('section')
  section.className = 'changelog-release'

  const head = document.createElement('h3')
  head.textContent = `${release.version}`
  const date = document.createElement('span')
  date.className = 'changelog-date'
  date.textContent = release.date
  head.appendChild(date)
  section.append(head)

  for (const group of release.sections) {
    const h4 = document.createElement('h4')
    h4.textContent = group.title
    section.append(h4)
    const ul = document.createElement('ul')
    for (const item of group.items) {
      const li = document.createElement('li')
      li.textContent = item
      ul.append(li)
    }
    section.append(ul)
  }
  return section
}

export function openChangelog(): void {
  if (!modal) modal = buildModal()
  modal.hidden = !modal.hidden
}
