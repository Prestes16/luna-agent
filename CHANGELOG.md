# Changelog

All notable changes to this project are documented here.
Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Preparing 1.0.0-rc1
- Added launch structure: LICENSE, PRIVACY, TERMS, SECURITY, CONTRIBUTING
- Hardened `.gitignore` covering venvs, local data, experimental artifacts

## [0.4.0] - 2026-04-30 - Luna V4 (closed beta)

### Added
- **Split Intelligence UI:** horizontal split with chat on the left and
  ExecutionPanel on the right, drag handle to resize
- **ExecutionPanel:** categorized log stream (BOUNTY / SOLANA / BROWSER /
  SYSTEM / CHAT) with dedicated colors and recharts visualizations
- **Skill BUILD_LAUNCHPAD:** Pump.fun, Raydium LaunchLab, Meteora DBC,
  Moonshot integrations
- **Skill SOLANA_MOBILE_DEFI:** Expo + MWA + Jupiter v6 + Pyth Hermes +
  Helius DAS patterns
- **Skill BUILD_MOBILE:** React Native + Expo scaffolding
- **17 new tools:** bounty_*, solana_*, browser_*
- **Template web3-ui-patterns.md:** 10 copy-paste components for PC + Mobile
- **Template solana-launchpad.md:** full launchpad integration guide
- **Thinking layer** + **Episodic memory** + **Action chain**
- **Projects system:** project management with context compression
- **Pay-Flow:** USDC / Solana billing via Helius webhook

### Changed
- RightPanel retired (deprecated stub), replaced by ExecutionPanel
- Sidebar with icon-only collapse (56 px)
- Luna logo preserved: purple/cyan gradient + glow + "ELITE AGENT v4"

### Fixed
- TOOL_ICONS map updated with real backend tool names (30 tools covered)
- 1:1 coherence between tool definitions and dispatcher `_fn_map`

## [0.3.0] - Prior beta milestones

See commit history for changes before V4.