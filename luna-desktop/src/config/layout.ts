export const SIDEBAR_EXPANDED_WIDTH = 220
export const SIDEBAR_COLLAPSED_WIDTH = 56

export const EXECUTION_PANEL_DEFAULT_WIDTH = 400
export const EXECUTION_PANEL_MIN_WIDTH = 300
export const EXECUTION_PANEL_MAX_WIDTH = 640
export const EXECUTION_PANEL_AUTO_COLLAPSE_WIDTH = 900
export const MAIN_CONTENT_MIN_WIDTH = 480

export function clampExecutionPanelWidth(width: number, availableWidth = Number.POSITIVE_INFINITY): number {
  const safeAvailable = Number.isFinite(availableWidth)
    ? Math.max(EXECUTION_PANEL_MIN_WIDTH, availableWidth - MAIN_CONTENT_MIN_WIDTH)
    : EXECUTION_PANEL_MAX_WIDTH

  return Math.round(Math.min(
    EXECUTION_PANEL_MAX_WIDTH,
    safeAvailable,
    Math.max(EXECUTION_PANEL_MIN_WIDTH, width),
  ))
}
