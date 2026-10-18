import type { CameraPresetName } from '../viewer/scene'
import { APP_VERSION } from './changelog'
import { openChangelog } from './changelog-view'

export interface PanelLayerSpec {
  id: string
  label: string
  visible: boolean
}

export interface PanelCallbacks {
  onLayerToggle: (id: string, visible: boolean) => void
  onCameraPreset: (preset: CameraPresetName) => void
  onStationChange: (stationId: string) => void
}

export const STATION_OPTIONS: Array<{ id: string; label: string }> = [
  { id: 'bicutan-real', label: 'Bicutan (CAD, real)' },
  { id: 'bicutan-placeholder', label: 'Bicutan (placeholder)' },
]

export interface PanelHandle {
  root: HTMLElement
  setStation: (name: string, layers: PanelLayerSpec[]) => void
  setStatus: (message: string, kind?: 'info' | 'error') => void
}

const CAMERA_BUTTONS: Array<{ preset: CameraPresetName; label: string }> = [
  { preset: 'orbit', label: 'Orbit' },
  { preset: 'walk', label: 'Walk' },
  { preset: 'top', label: 'Top' },
]

function el<K extends keyof HTMLElementTagNameMap>(
  tag: K,
  className?: string,
  text?: string,
): HTMLElementTagNameMap[K] {
  const node = document.createElement(tag)
  if (className) node.className = className
  if (text !== undefined) node.textContent = text
  return node
}

export function createPanel(host: HTMLElement, callbacks: PanelCallbacks): PanelHandle {
  const root = el('aside', 'panel')

  const title = el('h1', 'panel-title', 'NSCR EXPLORER')

  // Version badge + release-notes popup
  const versionBadge = el('button', 'version-badge', APP_VERSION) as HTMLButtonElement
  versionBadge.type = 'button'
  versionBadge.title = 'Release notes'
  versionBadge.addEventListener('click', () => openChangelog())
  const titleRow = el('div', 'title-row')
  titleRow.append(title, versionBadge)

  const stationLabel = el('div', 'panel-label', 'Station')
  const stationPicker = el('select', 'station-picker') as HTMLSelectElement
  for (const option of STATION_OPTIONS) {
    const opt = document.createElement('option')
    opt.value = option.id
    opt.textContent = option.label
    stationPicker.appendChild(opt)
  }
  stationPicker.addEventListener('change', () => callbacks.onStationChange(stationPicker.value))
  const stationName = el('h2', 'station-name', 'Loading…')

  const layersLabel = el('div', 'panel-label', 'Layers')
  const layerList = el('div', 'layer-list')

  const cameraLabel = el('div', 'panel-label', 'Camera presets')
  const buttonRow = el('div', 'btn-row')
  for (const { preset, label } of CAMERA_BUTTONS) {
    const button = el('button', 'preset-btn', label)
    button.type = 'button'
    button.dataset.preset = preset
    button.addEventListener('click', () => {
      for (const other of buttonRow.querySelectorAll('.preset-btn')) {
        other.classList.remove('active')
      }
      button.classList.add('active')
      callbacks.onCameraPreset(preset)
    })
    buttonRow.appendChild(button)
  }

  const status = el('div', 'panel-status', '')
  const hint = el('div', 'panel-hint', 'Drag to orbit · scroll to zoom · right-drag to pan')

  root.append(titleRow, stationLabel, stationPicker, stationName, layersLabel, layerList, cameraLabel, buttonRow, status, hint)
  host.appendChild(root)

  const setStation = (name: string, layers: PanelLayerSpec[]): void => {
    stationName.textContent = name
    layerList.replaceChildren()
    for (const layer of layers) {
      const row = el('label', 'layer-row')
      const checkbox = document.createElement('input')
      checkbox.type = 'checkbox'
      checkbox.checked = layer.visible
      checkbox.addEventListener('change', () => callbacks.onLayerToggle(layer.id, checkbox.checked))
      row.append(checkbox, el('span', 'layer-name', layer.label))
      layerList.appendChild(row)
    }
  }

  const setStatus = (message: string, kind: 'info' | 'error' = 'info'): void => {
    status.textContent = message
    status.classList.toggle('error', kind === 'error')
  }

  return { root, setStation, setStatus }
}
