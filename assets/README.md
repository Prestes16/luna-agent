# Assets

Official visual resources for Luna Agent.

## Required before release 1.0.0

- `icon.ico` — 256x256 multi-resolution (Windows)
- `icon.icns` — 1024x1024 base (macOS, built via `iconutil`)
- `icon.png` — 512x512 (Linux)
- `icon-tray.png` — 32x32 (system tray)
- `installer-banner.bmp` — 493x58 (NSIS installer header)
- `installer-sidebar.bmp` — 164x314 (NSIS installer sidebar)

## Theme

Moon motif with a gradient:
- Purple: `#7c3aed`
- Cyan:   `#00d4ff`
- Glow: `0 0 20px rgba(124,58,237,0.7), 0 0 40px rgba(0,212,255,0.15)`
- Transparent background

Visual reference: current inline logo at
`luna-desktop/src/components/Sidebar.tsx` lines 94-99.

## Generation

```bash
# Windows multi-res .ico from a 512 PNG
magick convert icon.png -define icon:auto-resize=256,128,64,48,32,16 icon.ico

# macOS .icns from an .iconset directory
iconutil -c icns icon.iconset
```