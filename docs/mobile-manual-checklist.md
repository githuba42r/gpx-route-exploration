# M7 mobile manual checklist (real phone)

Run on a physical phone (iOS Safari and/or Android Chrome) against a running build.
Automated tests emulate touch only; this pass covers real gesture behaviour.

## Library
- [ ] No horizontal scroll at any point; page does not zoom on input focus
- [ ] Filters button opens the filter drawer; closing it (button, backdrop) works
- [ ] Route cards are single column; Edit / Move / Delete are easy to tap

## Analysis
- [ ] No horizontal scroll; stats, sliders and preset select fit the screen
- [ ] Tap on the elevation profile moves the map marker
- [ ] Tap on a profile point pins it; tap outside dismisses the pin
- [ ] Touch-drag across the profile selects a zoom range (page does not scroll)
- [ ] Smoothing / gradient sliders drag without accidental page scroll

## Create
- [ ] One-finger drag pans the map (the sheet does not move)
- [ ] Pinch zooms the map; two-finger pan works
- [ ] Tap on empty map drops a waypoint
- [ ] Long-press on a marker opens the context menu once; releasing does not also tap
- [ ] Swipe up / down on the sheet handle expands / collapses the sheet; swipe on the list scrolls the list
- [ ] Reorder waypoints by dragging the ⋮⋮ handle (Sortable) in the full sheet
- [ ] Options toggle expands/collapses the secondary header controls
- [ ] Address autocomplete works with the on-screen keyboard (suggestions visible, not hidden)
- [ ] Convert dialog fits the screen and is usable
- [ ] Map resizes correctly when the sheet changes (no blank strips)
- [ ] Stop edit modal and CSV import dialog fit the screen, keyboard does not hide fields
- [ ] Rotating the phone (portrait/landscape) keeps layout usable; landscape shows map and list side by side

## General
- [ ] No horizontal scroll on any page
- [ ] All tap targets feel at least 44px; no mis-taps between adjacent buttons
- [ ] No text-selection / iOS callout popup on long-press of markers
