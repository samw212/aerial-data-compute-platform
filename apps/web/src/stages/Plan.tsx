/* Plan: cameras on the reviewed model, live coverage from the browser kernel,
 * Run on server to persist. docs/FRONTEND-DESIGN.md 2.5. */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type maplibregl from "maplibre-gl";
import { api } from "../api/client";
import type { CameraSpec, CoverageRun } from "../api/contracts";
import { usePatchCamera, useRunCoverage, useRuns, useScene, useStructures } from "../api/queries";
import { Shell } from "../app/Shell";
import { Bar, Chips, Dock, DockFooter, DockHeader, DockTabs, Empty, Hud, Slider, Tag, ToolRail, ViewControl } from "../components/ui";
import { lngLatToLocal } from "../geo";
import { heatmapCanvas } from "../heat";
import { DORI, TIERS_HARDEST_FIRST, blindPct, redundantPct, tierPct, type Tier } from "../kernel/stats";
import { rleToMask, useKernel } from "../kernel/useKernel";
import type { Camera, Grid, Occluder } from "../kernel/types";
import { doriRangeM, fPx } from "../kernel/optics";
import { GeoLayer, ImageLayer, MapView, useMap } from "../map/MapView";
import { camerasFC, gridCorners, structuresFC } from "../map/features";
import { Scene3D } from "../scene/Scene3D";
import { usePlanner } from "../state/planner";
import { useUi } from "../state/ui";
import { useStageContext } from "./useStageContext";

const TIER_COLOR: Record<Tier | "blind", string> = { identify: "#d63e34", recognise: "#eeb230", observe: "#48aa60", detect: "#4076c4", blind: "#3a3a40" };
const PREVIEW_SPACING = 1.0;
const REFINE_SPACING = 0.5;

export function PlanStage() {
  const ctx = useStageContext("Plan");
  const { venue, scenario, scenarioId } = ctx;
  const planner = usePlanner();
  const ui = useUi();
  const scene = useScene(scenarioId, planner.includeTents, planner.includeSeasonal, REFINE_SPACING);
  const structures = useStructures(scenario?.base_survey_id);
  const runs = useRuns(scenarioId);
  const patchCamera = usePatchCamera();
  const runCoverage = useRunCoverage();
  const compute = useKernel();
  const [tab, setTab] = useState("Cameras");
  const [cursor, setCursor] = useState<[number, number] | null>(null);
  const [serverRun, setServerRun] = useState<CoverageRun | null>(null);

  // Load the scenario's cameras into the working copy once.
  useEffect(() => {
    if (scenario && planner.scenarioId !== scenario.id) planner.load(scenario.id, scenario.cameras, scenario.include_seasonal);
  }, [scenario, planner]);

  const occluders = useMemo<Occluder[]>(() => (scene.data?.occluders ?? []).map((o) => ({ id: o.id, owner_id: o.owner_id, porosity: o.porosity, prim: o.prim as Occluder["prim"] })), [scene.data]);
  const gridAt = useCallback((spacing: number): Grid | null => {
    const g = scene.data?.grid;
    if (!g) return null;
    if (spacing === g.spacing) {
      const nx = Math.round((g.x_max - g.x_min) / g.spacing), nz = Math.round((g.z_max - g.z_min) / g.spacing);
      return { ...g, mask: rleToMask(g.mask_rle, nx * nz) };
    }
    // Coarser preview: the same extent, no mask (stats are for the refined run).
    return { x_min: g.x_min, x_max: g.x_max, z_min: g.z_min, z_max: g.z_max, spacing, mask: null };
  }, [scene.data]);

  // Live compute: 1 m while dragging, refine to 0.5 m once the hand pauses.
  const refine = useRef<number | null>(null);
  const cams = planner.cameras as unknown as Camera[];
  useEffect(() => {
    const g1 = gridAt(PREVIEW_SPACING);
    if (!g1 || !scene.data) return;
    compute(cams, occluders, g1, null, planner.evalHeight, planner.foreshorten);
    if (refine.current) window.clearTimeout(refine.current);
    refine.current = window.setTimeout(() => {
      const g = gridAt(REFINE_SPACING);
      if (g) compute(cams, occluders, g, null, planner.evalHeight, planner.foreshorten);
    }, 350);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cams, occluders, scene.data, planner.evalHeight, planner.foreshorten]);

  const preview = planner.preview;
  const heat = useMemo(() => (preview ? heatmapCanvas(preview.ppm, preview.count, preview.spacing === REFINE_SPACING ? gridAt(REFINE_SPACING)?.mask ?? null : null, preview.nx, preview.nz) : null), [preview, gridAt]);
  const heatUrl = useMemo(() => heat?.toDataURL() ?? "", [heat]);
  const corners = useMemo(() => (venue && preview ? gridCorners(venue, preview.grid) : null), [venue, preview]);

  const selectedCam = planner.cameras.find((c) => c.id === ui.selection) ?? null;
  const fc = useMemo(() => (venue ? camerasFC(venue, planner.cameras, ui.selection) : null), [venue, planner.cameras, ui.selection]);
  const sfc = useMemo(() => (venue ? structuresFC(venue, (structures.data ?? []).filter((s) => s.state === "accepted" || (planner.includeSeasonal && s.state === "seasonal")), null) : null), [venue, structures.data, planner.includeSeasonal]);
  const center: [number, number] = venue?.centroid_lon != null ? [venue.centroid_lon, venue.centroid_lat!] : [114.17, 22.32];
  const stats = preview?.stats;
  const extent = scene.data?.grid ?? { x_min: -70, x_max: 70, z_min: -45, z_max: 45 };

  const saveCamera = (c: CameraSpec) => {
    if (!scenarioId) return;
    patchCamera.mutate({ id: c.id, scenarioId, body: { position: c.position, pan_deg: c.pan_deg, tilt_deg: c.tilt_deg, focal_mm: c.focal_mm, enabled: c.enabled } }, { onSuccess: () => planner.markClean(c.id) });
  };
  const saveAll = () => planner.cameras.filter((c) => planner.dirty.has(c.id)).forEach(saveCamera);
  const runOnServer = () => {
    saveAll();
    if (!scenarioId) return;
    runCoverage.mutate({ scenarioId, body: { grid_spacing_m: REFINE_SPACING, include_tents: planner.includeTents, include_seasonal: planner.includeSeasonal, foreshorten: planner.foreshorten, eval_height_m: planner.evalHeight } }, { onSuccess: setServerRun });
  };
  const aimAt = (c: CameraSpec, x: number, z: number) => planner.updateCamera(c.id, { pan_deg: (Math.atan2(x - c.position.x, -(z - c.position.z)) * 180) / Math.PI });

  return (
    <Shell crumb={`${venue?.name ?? "…"} · ${scenario?.name ?? "…"}`} stages={ctx.links} status={planner.dirty.size ? <Tag tone="warn">unsaved</Tag> : <Tag tone="ok">saved</Tag>} jobs={planner.computing ? "● computing" : preview ? `○ ${preview.ms.toFixed(0)} ms` : ""}>
      {ui.view === "3d" ? (
        <Scene3D extent={extent} structures={(structures.data ?? []).filter((s) => s.state === "accepted")} cameras={planner.cameras} selected={ui.selection} onSelect={ui.select} heatCanvas={ui.layers.coverage ? heat : null} heatExtent={preview?.grid ?? null} />
      ) : (
        <MapView center={center} zoom={17.5} onMouseMove={setCursor} onClick={(ll, e) => {
          const f = e.target.queryRenderedFeatures(e.point, { layers: ["cam-pts"] })[0];
          if (f) { ui.select(String(f.properties.id)); return; }
          if (ui.tool === "target" && selectedCam && venue) { const [x, z] = lngLatToLocal(venue, ll[0], ll[1]); aimAt(selectedCam, x, z); ui.setTool("select"); return; }
          ui.select(null);
        }}>
          {heatUrl && corners && <ImageLayer id="coverage" url={heatUrl} coordinates={corners} visible={ui.layers.coverage ?? true} opacity={0.88} before="labels" />}
          {sfc && <GeoLayer id="structures" data={sfc} visible={ui.layers.structures ?? true} layers={[
            { id: "str-fill", type: "fill", paint: { "fill-color": "#5ee7ff", "fill-opacity": 0.15 } },
            { id: "str-line", type: "line", paint: { "line-color": "#5ee7ff", "line-width": 1.5 } },
          ]} />}
          {fc && <GeoLayer id="frusta" data={fc.frusta} visible={ui.layers.frusta ?? true} layers={[
            { id: "fru-fill", type: "fill", paint: { "fill-color": "#5ee7ff", "fill-opacity": ["case", ["==", ["get", "enabled"], 0], 0.02, 0.1] } },
            { id: "fru-line", type: "line", paint: { "line-color": ["case", ["==", ["get", "selected"], 1], "#ffb347", "#5ee7ff"], "line-width": ["case", ["==", ["get", "selected"], 1], 1.8, 1], "line-opacity": ["case", ["==", ["get", "enabled"], 0], 0.3, 1] } },
          ]} />}
          {fc && <GeoLayer id="cameras" data={fc.points} layers={[
            { id: "cam-pts", type: "circle", paint: { "circle-radius": ["case", ["==", ["get", "selected"], 1], 8, 6], "circle-color": ["case", ["==", ["get", "enabled"], 0], "#3a4656", ["==", ["get", "selected"], 1], "#ffb347", "#5ee7ff"], "circle-stroke-color": "#0e1116", "circle-stroke-width": 2 } },
            { id: "cam-lbl", type: "symbol", layout: { "text-field": ["get", "name"], "text-size": 11, "text-offset": [1.1, 0], "text-anchor": "left" }, paint: { "text-color": "#e8ecf1", "text-halo-color": "#0e1116", "text-halo-width": 1.2 } },
          ]} />}
          {venue && <CameraDrag venue={venue} cameras={planner.cameras} onMove={(id, x, z) => planner.updateCamera(id, { position: { ...planner.cameras.find((c) => c.id === id)!.position, x, z } })} onDrop={(id) => { const c = planner.cameras.find((k) => k.id === id); if (c) saveCamera(c); }} structures={structures.data ?? []} onSnap={(id, sid) => planner.updateCamera(id, { mount_structure_id: sid })} />}
        </MapView>
      )}
      <ToolRail tools={["cursor", "cam", "target", "tent", "layers"]} active={ui.tool === "select" ? "cursor" : ui.tool} onPick={(t) => ui.setTool(t === "cursor" ? "select" : t)} />
      <Chips items={[
        { key: "coverage", label: "Coverage", on: ui.layers.coverage ?? true, onToggle: () => ui.toggleLayer("coverage") },
        { key: "imagery", label: "Aerial imagery", on: ui.layers.imagery ?? false, onToggle: () => ui.toggleLayer("imagery") },
        { key: "structures", label: "Structures", on: ui.layers.structures ?? true, onToggle: () => ui.toggleLayer("structures") },
        { key: "frusta", label: "Frusta", on: ui.layers.frusta ?? true, onToggle: () => ui.toggleLayer("frusta") },
        { key: "tents", label: `Tents ${scenario?.tents.length ?? 0}`, on: planner.includeTents, onToggle: () => planner.setToggle("includeTents", !planner.includeTents) },
        { key: "seasonal", label: "Seasonal (summer)", on: planner.includeSeasonal, onToggle: () => planner.setToggle("includeSeasonal", !planner.includeSeasonal) },
      ]} />
      <div className="panel" style={{ position: "absolute", left: 58, top: 52, padding: "6px 10px", display: "flex", gap: 12, zIndex: 4 }}>
        {[["identify", "Identify ≥250"], ["recognise", "Recognise ≥125"], ["observe", "Observe ≥62"], ["detect", "Detect ≥25"], ["below", "below"], ["blind", "blind"]].map(([k, l]) => (
          <span key={k} className="row" style={{ gap: 5, fontSize: 10.5, color: "var(--color-ink-2)" }}><span style={{ width: 9, height: 9, borderRadius: 2, background: k === "below" ? "#78787e" : k === "blind" ? "#26262a" : TIER_COLOR[k as Tier], display: "inline-block" }} />{l}</span>
        ))}
      </div>
      <ViewControl view={ui.view} onPick={ui.setView} x="calc(50% - 190px)" />
      <Hud lines={[
        ui.tool === "target" ? "click the map to aim the selected camera" : ui.tool === "cam" ? "drag a camera; it snaps to a mast within 1.5 m" : cursor && venue ? (() => { const [x, z] = lngLatToLocal(venue, cursor[0], cursor[1]); return `local ${x.toFixed(1)}, ${z.toFixed(1)} m`; })() : "—",
        `targets ${planner.evalHeight} m above terrain · ${planner.foreshorten ? "foreshortening on" : "foreshortening OFF (overstates)"} · north up`,
      ]} />
      <Dock width={396}>
        <DockHeader eyebrow="Plan" title={scenario?.name ?? "…"} tag={serverRun ? <Tag tone="ok">run {serverRun.id.slice(0, 6)}</Tag> : <Tag>local preview</Tag>} meta={`on ${ctx.survey?.name ?? "…"} · ${occluders.length} occluders · ${scenario?.tents.length ?? 0} tents`} />
        <DockTabs tabs={["Cameras", "Coverage", "Runs"]} active={tab} onPick={setTab} />
        {tab === "Cameras" && (
          <div className="scroll" style={{ flex: 1 }}>
            {planner.cameras.map((c) => {
              const sel = c.id === ui.selection;
              const uniq = stats?.per_camera_unique_m2[c.id];
              return (
                <div key={c.id}>
                  <div onClick={() => ui.select(sel ? null : c.id)} className="row" style={{ gap: 8, padding: "7px 14px", borderBottom: "1px solid var(--color-line)", background: sel ? "var(--color-acc-dim)" : "transparent", fontSize: 12, cursor: "pointer" }}>
                    <span onClick={(e) => { e.stopPropagation(); planner.updateCamera(c.id, { enabled: c.enabled === false }); }} title="enable / disable" style={{ width: 7, height: 7, borderRadius: "50%", background: c.enabled === false ? "#2b3441" : "var(--color-acc)", flex: "0 0 7px" }} />
                    <span style={{ flex: 1, fontWeight: sel ? 600 : 500 }}>{c.name.replace("Camera on ", "")}</span>
                    <span className="m" style={{ fontSize: 11, color: "var(--color-ink-2)" }}>{c.focal_mm} mm</span>
                    <span className="m" style={{ fontSize: 11, width: 86, textAlign: "right" }}>{c.pan_deg.toFixed(0)}° / {c.tilt_deg.toFixed(0)}°</span>
                    <span className="m" style={{ fontSize: 11, width: 64, textAlign: "right" }}>{uniq != null ? `${uniq.toLocaleString(undefined, { maximumFractionDigits: 0 })} m²` : ""}</span>
                  </div>
                  {sel && (
                    <div style={{ padding: "10px 14px", display: "grid", gridTemplateColumns: "repeat(2, minmax(0,1fr))", gap: "10px 14px", background: "var(--color-panel-2)" }}>
                      <Slider label="Pan" value={c.pan_deg} min={-180} max={180} step={1} unit="°" onChange={(v) => planner.updateCamera(c.id, { pan_deg: v })} />
                      <Slider label="Tilt" value={c.tilt_deg} min={0} max={80} step={1} unit="°" onChange={(v) => planner.updateCamera(c.id, { tilt_deg: v })} />
                      <Slider label="Height" value={c.position.y} min={2} max={20} step={0.5} unit=" m" onChange={(v) => planner.updateCamera(c.id, { position: { ...c.position, y: v } })} />
                      <Slider label="Focal" value={c.focal_mm} min={2.8} max={50} step={0.1} unit=" mm" onChange={(v) => planner.updateCamera(c.id, { focal_mm: v })} />
                      <div className="row" style={{ gridColumn: "1 / -1", gap: 6 }}>
                        <button className="btn" style={{ height: 26 }} onClick={() => aimAt(c, 0, 0)}>Aim at centre</button>
                        <button className={`btn ${ui.tool === "target" ? "acc" : ""}`} style={{ height: 26 }} onClick={() => ui.setTool(ui.tool === "target" ? "select" : "target")}>Aim at point</button>
                        <button className="btn acc" style={{ height: 26, marginLeft: "auto" }} disabled={!planner.dirty.has(c.id)} onClick={() => saveCamera(c)}>Save</button>
                      </div>
                      <div className="m" style={{ gridColumn: "1 / -1", fontSize: 10.5, color: "var(--color-ink-3)" }}>
                        {c.mount_structure_id ? `mount ${(structures.data ?? []).find((s) => s.id === c.mount_structure_id)?.name ?? c.mount_structure_id.slice(0, 8)}` : "free-standing"} · Detect to {doriRangeM(fPx(c.focal_mm, c.res_y, c.sensor_h_mm), DORI.detect).toFixed(0)} m · Observe {doriRangeM(fPx(c.focal_mm, c.res_y, c.sensor_h_mm), DORI.observe).toFixed(0)} m
                      </div>
                    </div>
                  )}
                </div>
              );
            })}
            {!planner.cameras.length && <Empty title="No cameras" hint="Camera creation from mount points arrives with the mount picker; the seeded scenario has four." />}
          </div>
        )}
        {tab === "Coverage" && (
          <div style={{ padding: "12px 14px", display: "flex", flexDirection: "column", gap: 6, flex: 1 }}>
            <div className="row" style={{ justifyContent: "space-between", marginBottom: 4 }}><span className="lbl">Coverage</span><Tag>{serverRun ? `server · ${serverRun.grid_spacing_m} m` : `local preview · ${preview?.spacing ?? "—"} m · ${preview?.ms.toFixed(0) ?? "—"} ms`}</Tag></div>
            {stats ? (
              <>
                {TIERS_HARDEST_FIRST.map((t) => <TierRow key={t} label={t[0]!.toUpperCase() + t.slice(1)} pct={tierPct(stats, t)} m2={stats.tier_area_m2[t]} color={TIER_COLOR[t]} />)}
                <TierRow label="Blind" pct={blindPct(stats)} m2={stats.blind_m2} color={TIER_COLOR.blind} />
                <TierRow label="Seen by 2+" pct={redundantPct(stats)} m2={stats.redundant_2plus_m2} color="#98a2b3" />
                <div className="m" style={{ fontSize: 10.5, color: "var(--color-ink-3)", marginTop: 4 }}>kernel {stats.kernel_version} · {stats.cells.toLocaleString()} cells · {stats.area_m2.toLocaleString(undefined, { maximumFractionDigits: 0 })} m² AOI · mean {stats.mean_ppm.toFixed(1)} px/m</div>
              </>
            ) : <Empty title={scene.isLoading ? "Loading scene…" : "Computing…"} />}
            <div className="hr" style={{ margin: "8px 0" }} />
            <Slider label="Eval height above terrain" value={planner.evalHeight} min={0} max={3} step={0.1} unit=" m" onChange={(v) => usePlanner.setState({ evalHeight: v })} />
            <label className="row" style={{ gap: 8, fontSize: 12 }}><input type="checkbox" checked={planner.foreshorten} onChange={(e) => planner.setToggle("foreshorten", e.target.checked)} style={{ accentColor: "var(--color-acc)" }} />Foreshortening (off overstates by about a third)</label>
          </div>
        )}
        {tab === "Runs" && (
          <div className="scroll" style={{ flex: 1 }}>
            {(runs.data ?? []).map((r) => (
              <div key={r.id} onClick={() => setServerRun(r)} style={{ padding: "8px 14px", borderBottom: "1px solid var(--color-line)", cursor: "pointer", background: serverRun?.id === r.id ? "var(--color-acc-dim)" : undefined }}>
                <div className="row" style={{ justifyContent: "space-between" }}><span className="m" style={{ fontSize: 12 }}>{r.id.slice(0, 8)}</span><span className="m" style={{ fontSize: 10.5, color: "var(--color-ink-3)" }}>{r.computed_at?.slice(0, 16).replace("T", " ")}</span></div>
                <div className="m" style={{ fontSize: 11, color: "var(--color-ink-2)", marginTop: 2 }}>{r.grid_spacing_m} m · tents {r.include_tents ? "on" : "off"} · detect {(100 * (r.stats.tier_area_m2.detect ?? 0) / r.stats.area_m2).toFixed(1)}% · blind {(100 * r.stats.blind_m2 / r.stats.area_m2).toFixed(1)}% · kernel {r.kernel_version}</div>
              </div>
            ))}
            {!runs.data?.length && <Empty title="No server runs yet" hint="Run on server persists a run that a report can cite." />}
          </div>
        )}
        <DockFooter>
          <button className="btn acc" onClick={runOnServer} disabled={runCoverage.isPending}>{runCoverage.isPending ? "Running…" : "Run on server"}</button>
          <button className="btn" onClick={saveAll} disabled={!planner.dirty.size}>Save {planner.dirty.size ? planner.dirty.size : ""}</button>
          {ctx.links.find((l) => l.stage === "Report")?.to && <a className="btn" style={{ marginLeft: "auto" }} href={ctx.links.find((l) => l.stage === "Report")!.to}>Report →</a>}
        </DockFooter>
      </Dock>
    </Shell>
  );
}

function TierRow({ label, pct, m2, color }: { label: string; pct: number; m2: number; color: string }) {
  return (
    <div className="row" style={{ gap: 8, padding: "2px 0" }}>
      <span style={{ width: 9, height: 9, borderRadius: 2, background: color, flex: "0 0 9px" }} />
      <span style={{ width: 72, fontSize: 12 }}>{label}</span>
      <Bar pct={pct} color={color} width="auto" />
      <span className="m" style={{ width: 46, textAlign: "right", fontSize: 12 }}>{pct.toFixed(1)}%</span>
      <span className="m" style={{ width: 64, textAlign: "right", fontSize: 11, color: "var(--color-ink-2)" }}>{m2.toLocaleString(undefined, { maximumFractionDigits: 0 })} m²</span>
    </div>
  );
}

/** Drag a camera on the map; snap to a pole primitive within 1.5 m and record the mount. */
function CameraDrag({ venue, cameras, structures, onMove, onDrop, onSnap }: { venue: NonNullable<ReturnType<typeof useStageContext>["venue"]>; cameras: CameraSpec[]; structures: { id: string; name: string; state: string; primitive: { kind: string; cx?: number; cz?: number; r?: number } }[]; onMove: (id: string, x: number, z: number) => void; onDrop: (id: string) => void; onSnap: (id: string, structureId: string | null) => void }) {
  const map = useMap();
  const tool = useUi((s) => s.tool);
  useEffect(() => {
    if (!map) return;
    let dragging: string | null = null;
    const down = (e: maplibregl.MapMouseEvent) => {
      if (tool !== "cam" && tool !== "select") return;
      const f = map.queryRenderedFeatures(e.point, { layers: ["cam-pts"] })[0];
      if (!f) return;
      dragging = String(f.properties.id);
      map.dragPan.disable();
      map.getCanvas().style.cursor = "grabbing";
    };
    const move = (e: maplibregl.MapMouseEvent) => {
      if (!dragging) return;
      let [x, z] = lngLatToLocal(venue, e.lngLat.lng, e.lngLat.lat);
      let snap: string | null = null;
      for (const s of structures) {
        if (s.primitive.kind !== "cylinder" || s.state !== "accepted") continue;
        const d = Math.hypot(x - s.primitive.cx!, z - s.primitive.cz!);
        if (d < 1.5) { const r = (s.primitive.r ?? 0.3) + 0.75; const a = Math.atan2(z - s.primitive.cz!, x - s.primitive.cx!); x = s.primitive.cx! + r * Math.cos(a); z = s.primitive.cz! + r * Math.sin(a); snap = s.id; break; }
      }
      onMove(dragging, x, z);
      onSnap(dragging, snap);
    };
    const up = () => {
      if (!dragging) return;
      const id = dragging;
      dragging = null;
      map.dragPan.enable();
      map.getCanvas().style.cursor = "";
      onDrop(id);
    };
    map.on("mousedown", down); map.on("mousemove", move); map.on("mouseup", up);
    return () => { map.off("mousedown", down); map.off("mousemove", move); map.off("mouseup", up); };
  }, [map, tool, venue, cameras, structures, onMove, onDrop, onSnap]);
  return null;
}

export { api as _api };
