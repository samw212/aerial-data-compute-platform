# ADCP — Frontend Design  (v3, 2026-09-04)

`apps/web`. The design for approval before code is written. Mockups: the design
canvas linked from my message. What changed from v2: Map, 3D and Review are one
stage (**Model**); the sidebar-and-cards layout and the borrowed design language are
gone; the layout is built from what this system actually does.

---

## 1. The idea: the site is the page

Everything a surveyor or planner does here happens *on the site* — photos are taken
over it, the model is of it, structures stand on it, cameras look across it. So the
site fills the screen on every stage, and the interface floats around it:

```
┌ top bar ──────────────────────────────────────────────────────────────────────┐
│ ADCP / venue · survey · [status]     ● Capture ─ ● Process ─ ◉ Model ─ ○ Plan ─ ○ Report      ⌘K  jobs  user │
├───────────────────────────────────────────────────────────────────────────────┤
│ ▢ tool   [layer chips …]                                            ┌ dock ──┐│
│ ▢ rail                                                              │ stage  ││
│ ▢                     V I E W P O R T                               │ context││
│ ▢          plan (north-up on Google Maps) ⇄ 3D (orbit) ⇄ photo      │ tabs   ││
│                                                                     │ list / ││
│   HUD  E N H · GSD · accuracy          [ Plan | 3D | Photo | ⊕ ]    │ detail ││
│ ┌ strip: gallery · console · evidence · timeline ─────────────────┐ │ actions││
│ └─────────────────────────────────────────────────────────────────┘ └────────┘│
└───────────────────────────────────────────────────────────────────────────────┘
```

| Region | Purpose | Behaviour |
|---|---|---|
| **Top bar** (44 px) | identity, breadcrumb, **the pipeline as navigation**, search, jobs, user | The five stages are steps with state: done ●, current ◉, locked ○. Clicking a done stage revisits it; a locked stage shows why (`qa`, `processing`). |
| **Viewport** | the site | One scene with three view modes: **Plan** (orthographic, north-up, on the Google basemap), **3D** (orbit / walk), **Photo** (through a solved shot). Same layers and selection in all three. |
| **Tool rail** (left) | the verbs of the current stage | select, measure, place camera, draw structure, clip, pin GCP, photo. One active tool; keyboard equivalents. |
| **Layer chips** (top of viewport) | what is drawn | toggle chips with a `⋯` for opacity and style; the set changes per stage but the chip is the same control everywhere. |
| **Dock** (right, 340–420 px) | the stage's context | header (stage, subject, status), tabs, a list or form, a detail card for the selection, primary actions pinned at the bottom. |
| **Strip** (bottom, collapsible) | anything sequential | photo gallery, processing console, evidence crops, run history. Collapses to a 28 px handle. |
| **HUD** (bottom-left, mono) | instrument read-outs | cursor E/N/H, GSD, tolerance, frame rate in 3D. Text over the scene, no box. |
| **View control** (bottom-centre) | Plan / 3D / Photo + compass | the one control that is always in the same place. |

No page scrolls. Panels scroll internally. Everything not the site is translucent
graphite so the imagery stays the brightest thing on screen.

---

## 2. Stages

```
/                                 Portfolio     venue map + facility health dock
/venues/:id/surveys/:sid/capture  Capture       footprints · flight · QA · GCP · gallery
/…/process                        Process       node · stages · gates · assets · console
/…/model                          Model         Map + 3D + Review + Measure, one viewport
/…/plan/:scenarioId               Plan          cameras · coverage · tents · runs · compare (split view)
/…/report                         Report        run history · saved comparisons · PDF
/jobs · /admin                    System        (dock-only pages over the venue map)
```

### 2.1 Portfolio

Viewport: Google map of all venues, markers coloured by coverage health, hover card
with facilities and their latest percentages. Dock: organisation header with venues
/ on-target / surveys-due; tabs Facilities · Surveys · Jobs; facility rows worst
first with the bar against target and a `stale` tag. Chips: Roadmap · Satellite ·
Dark · Coverage health · Survey age.

### 2.2 Capture   *(the "stacked images before stitching" view)*

Viewport (Plan): every accepted photo's **ground footprint** from GPS, altitude,
gimbal and sensor, drawn as a translucent rectangle in the accent colour so overlap
reads as density; the flight line in capture order; oblique orbit shots as amber
triangles; GCPs as amber rings. Hover a footprint → thumbnail card; click → the
gallery scrolls to it and Photo view is one keystroke away. A heading histogram
chip shows the cross-hatch. After processing, a *Solved shots* chip replaces
footprints with exact poses.

Dock: survey header; tabs **QA** (counts, overlap bars with warn/block marks,
sharpness, blocking items in red with the rule, warnings in amber, *Acknowledge*),
**Ground control** (GCP table, marking view opens in the viewport in Photo mode with
pixel zoom), **Upload** (drop zone, manifest hashing, resumable parts, the
disk estimate). *Process →* pinned at the bottom, disabled while blocking is
non-empty, with the reason.

Strip: the gallery as a filmstrip with sharpness / state tags; filters; `r` reject,
`u` restore.

### 2.3 Process   *(the ODM task view)*

Viewport: the site as it becomes known. In **Plan**, solved shots appear as the sparse
reconstruction completes and the preview orthophoto fades in as texturing runs. In
**3D**, the sparse point cloud and the camera frusta appear as soon as the
structure-from-motion stage finishes, and the dense cloud replaces it when
densification finishes — you watch the model appear while ODM is still texturing.
**Photo** works for any solved shot. Dock:
task header (node, GPU, quality, ODM version); tabs **Stages** (the ODM stage list
with the §9.2 progress mapping, elapsed, ETA, disk), **Gates** (§10.9 acceptance
table filling as results arrive; a failing gate names itself; the survey never
completes with a warning), **Assets** (every artefact with size, sha256, open in
Model), **Options** (what was sent to ODM, commit, seed). Actions: restart with
options, cancel. Strip: the live console, mono, pause / search / download,
persisted per task, survives reload and worker restart.

### 2.4 Model   *(Map + 3D + Review + Measure — one stage)*

Viewport layers (chips): Orthophoto · DSM · DTM · Contours · Point cloud · Textured
mesh · Structures · Shots · Mount points · Google 3D Tiles · Splat · Coverage. View
modes: **Plan** on the basemap, **3D** orbit with EDL point cloud and Google
Photorealistic 3D Tiles around the venue, **Photo** through any shot (click a frustum
or an evidence crop) with the model faded under the image.

Dock tabs:
- **Structures** — the review list: name, class, confidence bar, state, `accuracy_m`,
  *insufficient for mount design*; filters; the detail card for the selection with
  dimensions and tolerance, porosity, mountable, and the verbs Accept / Reject
  (typed) / Seasonal / Reclassify (→ refit) / Adjust (gizmo). Keyboard review:
  `a` `r`→`1 2 3` `s` `c` `j`/`k`.
- **Shots** — solved cameras; select → highlighted in the viewport; open image; photo
  mode; "shot coverage" shading of how many images see each spot.
- **Measure** — type chips (3D distance, horizontal, vertical, height AGL, area,
  volume, clearance, profile); the active measurement with each point's snap mode
  and σ, the survey's σ, the value **always with its tolerance**; saved measurements
  for this survey; disabled with an explanation when `georef = 'none'`.
- **Layers** — opacity, colour ramps, point size and budget, contour interval.

Strip: **Evidence** for the selected structure — the best source crops with the
bbox, incidence angle; click → Photo view through that shot. Mount points appear
as markers on accepted mountable structures and use the same review verbs.

### 2.5 Plan

Viewport: the DORI heatmap draped on the site at eval height, accepted structures
only, cameras with frusta, tents, proposed masts hatched. **Drag placement** (§12.7):
ray-cast against primitives → mesh → terrain with the readout (surface, height AGL,
`accuracy_m`); a terrain drop opens the proposed-mast dialog and creates the occluder;
a drop on a rejected structure warns. Dock tabs: **Cameras** (compact rows, the editor
for the selection: pan / tilt / height on pole / lens catalogue, aim at centre or
point), **Coverage** (tier bars, blind, redundancy, per-camera unique area,
`kernel_version`, `local preview` vs `run <id>`), **Tents** (template, 3 × 4 preset,
drag and rotate), **Runs** (persisted runs on this scenario). Actions: Run on server,
Optimise…, Compare, PDF (persisted run only). Live compute in the Web Worker at 1 m
while dragging, refine to 0.5 m on pause.

### 2.6 Report

Report is the deliverable stage for **one facility**: the persisted coverage runs of
its scenarios (who ran what, when, with which kernel), and the PDF export (§15.2:
accuracy statement, structure schedule, camera schedule, coverage plan per tier,
blind-spot plan, redundancy plan). It never compares venues.

Comparing two runs of the same facility — tents up against tents down, before and
after the optimiser — is a **split-view mode inside Plan** (*Compare with…*): the two
runs side by side on the same grid, the delta map, the tier table with Δ and the
newly-blind area. Report lists the comparisons that were saved so the PDF can include
them.

---

## 3. Design language (ADCP's own)

**Surfaces.** Graphite, not black: canvas `#0e1116`, panels `rgba(19,23,30,.88)` with
backdrop blur, hairlines `rgba(255,255,255,.09)`, 6 px radii — instrument, not SaaS
card. The viewport is always the brightest region.

**Type.** **Archivo** for all UI (variable width: condensed labels, wide display),
**DM Mono** for every value, coordinate, id and tolerance. Eyebrow labels 10.5 px,
600, 0.14 em tracking, uppercase. Body 12.5 px. Titles 18–20 px, 700.

**Colour.** One accent, laser cyan `#5ee7ff` — selection, active tool, footprints,
shots, primary action. Status: ok `#3ddc84`, warn `#ffb347`, bad `#ff5c5c`, as small
tags. DORI palette (`#d63e34 #eeb230 #48aa60 #4076c4 #78787e #26262a`) only in the
heatmap and its legend; cyan was chosen because it sits between the DORI hues and
reads as "tool", never as a coverage tier. Review states: accepted cyan, pending grey,
rejected red, seasonal green, proposed violet, in the viewport and the dock alike.

**Density.** Rows 30–32 px, tables without gridlines, 4 px meters, tags not badges.
Keyboard verbs shown as `kbd` hints where they apply.

**Motion.** Panels slide 6 px on stage change; layer toggles cross-fade; nothing
else. Frame rate is the feature.

**Icons.** Stroke SVG on a 24 px grid, 1.6 px stroke, one set.

---

## 4. Stack

| Concern | Choice |
|---|---|
| Build | Vite 5, React 18, TypeScript strict |
| Styling | Tailwind CSS v4 with the tokens above in one `@theme` block; CSS variables for panel translucency |
| 2D map | **MapLibre GL** with the Hong Kong Lands Department GeoData Store tiles (topographic basemap, aerial imagery, labels; free, no key) behind a `MapProvider` interface; a Google Maps provider can be added later behind the same interface if a key ever exists |
| 3D | three.js + react-three-fiber; `3d-tiles-renderer` for our point-cloud tiles (and, later, any 3D Tiles city model: Google's needs a key, the CSDI portal's Hong Kong building models are an open alternative to evaluate); glTF mesh; optional `@mkkellogg/gaussian-splats-3d` |
| Plan ⇄ 3D | one scene graph; Plan is an orthographic camera looking down with the basemap as a ground plane, so layers and selection are shared, and the transition is a camera move |
| Server state | TanStack Query |
| Local state | zustand: `stage`, `view`, `layers`, `selection`, `planner`, `review` |
| Routing | react-router 6, stage in the path, view mode and selection in the query |
| Types | `src/api/contracts.ts` generated from `packages/contracts` |
| Kernel | `src/kernel/` TS port, Web Worker, parity test |
| Tests | Vitest, Playwright |

---

## 5. Map integration

No Google key is available, so the basemap is the **Hong Kong Lands Department GeoData
Store**, which is free and needs no key:

| Layer | Tiles (EPSG:3857, XYZ) |
|---|---|
| Topographic basemap | `https://mapapi.geodata.gov.hk/gs/api/v1.0.0/xyz/basemap/wgs84/{z}/{x}/{y}.png` |
| Aerial imagery | `https://mapapi.geodata.gov.hk/gs/api/v1.0.0/xyz/imagery/wgs84/{z}/{x}/{y}.png` |
| Labels (English / Chinese) | `https://mapapi.geodata.gov.hk/gs/api/v1.0.0/xyz/label/hk/en/wgs84/{z}/{x}/{y}.png` |

Attribution as the Lands Department requires is rendered on the map. Our own layers
are XYZ tiles in EPSG:3857 (ortho, DSM, DTM, coverage; contours as vector tiles) so
any basemap can sit under them. `MapProvider` is an interface with one implementation
today (MapLibre); a Google provider and the photorealistic 3D city layer are deferred
until a key exists, and the 3D-tiles surroundings chip is hidden until then. The
CSDI portal's open 3D building models for Hong Kong are the candidate keyless
alternative for surroundings, to be evaluated in Phase 3.

## 6. Scene, kernel, state

Local ENU metres, Y up; the API delivers coordinates rebased to `venue.origin`; the
renderer never sees a projected easting. Camera basis per CLAUDE.md
(`forward = (sin pan·cos tilt, −sin tilt, −cos pan·cos tilt)`); Plan view shows pan 0
as up so T9 reads visually. `src/kernel/` mirrors `packages/coverage` module for
module with the same `KERNEL_VERSION`, asserted by a test; runs in a Web Worker with
transferable arrays; parity < 0.5 % of cells differ by > 1 px/m.

```
TanStack Query   venues, surveys, images, tasks, artefacts, structures, scenarios, runs
zustand          stage · view mode · layers (per stage, per user) · selection ·
                 planner (cameras, tents, preview result) · review (filters, cursor)
WebSocket        /ws/jobs/{id}: progress + console → invalidates queries on completion
```

---

## 7. Acceptance

- Kernel parity < 0.5 % of cells differ by > 1 px/m; planner drag preview < 100 ms.
- Plan ⇄ 3D ⇄ Photo keep layers and selection; the transition is under 400 ms.
- Capture draws 1,000 footprints at 60 fps; gallery virtualised at 5,000 images.
- Console keeps up with ODM; reload and worker restart resume the stream.
- 3D: synthetic cloud first frame < 3 s; frusta clickable; Google 3D Tiles within 5 s
  when on; everything works with the chip off and no key.
- Review entirely by keyboard; every dimension carries its tolerance.
- T9 visually; T8 in the UI; a terrain drop creates mount point + proposed mast.
- Initial bundle < 1.5 MB gzip; 3D code split.
- Playwright e2e across all five stages against the fixture backend, with and
  without a Google key.
