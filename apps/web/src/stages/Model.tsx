/* Model: Map + 3D + Review + Measure in one viewport. docs/FRONTEND-DESIGN.md 2.4. */

import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { usePatchStructure, useStructures } from "../api/queries";
import type { Structure } from "../api/contracts";
import { Shell } from "../app/Shell";
import { Bar, Chips, Dock, DockFooter, DockHeader, DockTabs, Empty, Hud, Kv, Strip, Tag, ToolRail, ViewControl } from "../components/ui";
import { lngLatToLocal, localToLngLat, ringToLngLat, storageRingToLocal } from "../geo";
import { GeoLayer, MapView } from "../map/MapView";
import { STATE_COLOR, ringsFC, structuresFC } from "../map/features";
import { Scene3D } from "../scene/Scene3D";
import { useUi } from "../state/ui";
import { STATUS_TONE, useStageContext } from "./useStageContext";
import { useFacilities } from "../api/queries";

const TONE: Record<string, "acc" | "mute" | "bad" | "ok" | "proposed"> = { accepted: "acc", pending: "mute", rejected: "bad", seasonal: "ok" };

export function ModelStage() {
  const ctx = useStageContext("Model");
  const { venue, survey, surveyId } = ctx;
  const structures = useStructures(surveyId);
  const facilities = useFacilities(ctx.venueId);
  const patch = usePatchStructure();
  const ui = useUi();
  const [tab, setTab] = useState("Structures");
  const [filter, setFilter] = useState<"all" | "pending" | "mountable">("all");
  const [cursor, setCursor] = useState<[number, number] | null>(null);
  const [rejecting, setRejecting] = useState<string | null>(null);

  const list = useMemo(() => {
    const all = structures.data ?? [];
    return all.filter((s) => (filter === "pending" ? s.state === "pending" : filter === "mountable" ? s.mountable : true)).sort((a, b) => a.name.localeCompare(b.name));
  }, [structures.data, filter]);
  const selected = list.find((s) => s.id === ui.selection) ?? (structures.data ?? []).find((s) => s.id === ui.selection) ?? null;

  const review = useCallback((s: Structure, body: Record<string, unknown>) => patch.mutate({ id: s.id, body: body as never }), [patch]);

  // Keyboard review: a accept · r reject then 1/2/3 · s seasonal · j/k move.
  useEffect(() => {
    const h = (e: KeyboardEvent) => {
      if ((e.target as HTMLElement)?.tagName === "INPUT") return;
      const idx = list.findIndex((s) => s.id === ui.selection);
      if (e.key === "j" || e.key === "k") {
        const n = Math.max(0, Math.min(list.length - 1, idx + (e.key === "j" ? 1 : -1)));
        if (list[n]) ui.select(list[n]!.id);
        return;
      }
      if (!selected) return;
      if (rejecting) {
        const reason = ({ "1": "noise", "2": "transient", "3": "duplicate" } as Record<string, string>)[e.key];
        if (reason) review(selected, { state: "rejected", reject_reason: reason });
        setRejecting(null);
        return;
      }
      if (e.key === "a") review(selected, { state: "accepted" });
      if (e.key === "s") review(selected, { state: "seasonal" });
      if (e.key === "r") setRejecting(selected.id);
      if (e.key === "Escape") ui.select(null);
    };
    window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
  }, [list, selected, rejecting, review, ui]);

  const fc = useMemo(() => (venue ? structuresFC(venue, structures.data ?? [], ui.selection) : null), [venue, structures.data, ui.selection]);
  const facilityRings = useMemo(() => (venue ? (facilities.data ?? []).map((f) => storageRingToLocal(venue, f.boundary)) : []), [venue, facilities.data]);
  const facFC = useMemo(() => (venue ? ringsFC(venue, facilityRings) : null), [venue, facilityRings]);
  const extent = useMemo(() => {
    const ring = facilityRings[0] ?? [[-70, -45], [70, 45]];
    const xs = ring.map((p) => p[0]), zs = ring.map((p) => p[1]);
    return { x_min: Math.min(...xs) - 15, x_max: Math.max(...xs) + 15, z_min: Math.min(...zs) - 10, z_max: Math.max(...zs) + 10 };
  }, [facilityRings]);
  const center: [number, number] = venue ? localToLngLat(venue, 0, 0) : [114.17, 22.32];
  const bounds = useMemo(() => (venue && facilityRings[0] ? ringToLngLat(venue, facilityRings[0]) : venue ? ringToLngLat(venue, [[-70, -45], [70, -45], [70, 45], [-70, 45]]) : null), [venue, facilityRings]);
  const counts = useMemo(() => {
    const all = structures.data ?? [];
    return { total: all.length, pending: all.filter((s) => s.state === "pending").length };
  }, [structures.data]);

  return (
    <Shell crumb={`${venue?.name ?? "…"} · ${survey?.name ?? "…"}`} stages={ctx.links} status={survey && <Tag tone={STATUS_TONE[survey.status] ?? "mute"}>{survey.status.replace("_", " ")}</Tag>}>
      {ui.view === "3d" ? (
        <Scene3D extent={extent} structures={structures.data ?? []} cameras={[]} selected={ui.selection} onSelect={ui.select} />
      ) : (
        <MapView center={center} zoom={17.5} bounds={bounds} onMouseMove={setCursor} onClick={(_, e) => {
          const f = e.target.queryRenderedFeatures(e.point, { layers: ["str-fill"] })[0];
          ui.select(f ? String(f.properties.id) : null);
        }}>
          {facFC && <GeoLayer id="facility" data={facFC} layers={[{ id: "fac-line", type: "line", paint: { "line-color": "#5ee7ff", "line-width": 1.5, "line-dasharray": [4, 3], "line-opacity": 0.8 } }]} />}
          {fc && <GeoLayer id="structures" data={fc} visible={ui.layers.structures} layers={[
            { id: "str-fill", type: "fill", paint: { "fill-color": ["get", "color"], "fill-opacity": ["case", ["==", ["get", "selected"], 1], 0.45, ["==", ["get", "porous"], 1], 0.08, 0.2] } },
            { id: "str-line", type: "line", paint: { "line-color": ["get", "color"], "line-width": ["case", ["==", ["get", "selected"], 1], 2.5, 1.5], "line-dasharray": ["case", ["==", ["get", "state"], "rejected"], ["literal", [2, 2]], ["literal", [1, 0]]] } },
            { id: "str-lbl", type: "symbol", minzoom: 18, layout: { "text-field": ["get", "name"], "text-size": 10.5, "text-offset": [0, 1.2] }, paint: { "text-color": "#98a2b3", "text-halo-color": "#0e1116", "text-halo-width": 1 } },
          ]} />}
        </MapView>
      )}
      <ToolRail tools={["cursor", "ruler", "draw", "photo", "layers"]} active={ui.tool === "select" ? "cursor" : ui.tool} onPick={(t) => ui.setTool(t === "cursor" ? "select" : t)} />
      <Chips items={[
        { key: "imagery", label: "Aerial imagery", on: ui.layers.imagery ?? false, onToggle: () => ui.toggleLayer("imagery") },
        { key: "structures", label: "Structures", on: ui.layers.structures ?? true, onToggle: () => ui.toggleLayer("structures") },
        { key: "labels", label: "Labels", on: ui.layers.labels ?? true, onToggle: () => ui.toggleLayer("labels") },
      ]} />
      <ViewControl view={ui.view} onPick={ui.setView} bottom={ui.stripOpen ? 174 : 12} x="calc(50% - 170px)" />
      <Hud bottom={ui.stripOpen ? 174 : 12} lines={[
        cursor && venue ? (() => { const [x, z] = lngLatToLocal(venue, cursor[0], cursor[1]); return `E ${(venue.origin_x + x).toFixed(2)} · N ${(venue.origin_y - z).toFixed(2)} · local ${x.toFixed(1)}, ${z.toFixed(1)}`; })() : "—",
        `${survey?.georef ?? "—"} · EPSG:${venue?.srid ?? "—"} · ${venue?.height_datum ?? ""}`,
      ]} />
      <div style={{ position: "absolute", left: 58, bottom: ui.stripOpen ? 230 : 68, fontSize: 10.5, color: "var(--color-ink-3)", zIndex: 4 }}>
        Keys <span className="kbd">a</span> accept · <span className="kbd">r</span> reject → <span className="kbd">1</span> noise <span className="kbd">2</span> transient <span className="kbd">3</span> duplicate · <span className="kbd">s</span> seasonal · <span className="kbd">j</span>/<span className="kbd">k</span> next
        {rejecting && <span className="tag t-bad" style={{ marginLeft: 8 }}>reject: press 1, 2 or 3</span>}
      </div>
      <Strip open={ui.stripOpen} right={420}>
        <div className="row" style={{ padding: "8px 12px 6px", justifyContent: "space-between" }}>
          <div className="row"><span className="lbl">Evidence{selected ? ` · ${selected.name}` : ""}</span>{selected && <Tag>{selected.evidence?.length ?? 0} views</Tag>}</div>
          <button className="btn" style={{ height: 22, fontSize: 11 }} onClick={ui.toggleStrip}>hide</button>
        </div>
        <div style={{ padding: "0 12px", color: "var(--color-ink-3)", fontSize: 12 }}>
          {selected?.evidence?.length ? "Source crops arrive with the image store (M6)." : "Evidence crops are produced by structure extraction (M10). For the synthetic survey there are none."}
        </div>
      </Strip>
      <Dock width={396}>
        <DockHeader eyebrow="Model" title={survey?.name ?? "…"} tag={survey && <Tag tone={STATUS_TONE[survey.status] ?? "mute"}>{survey.status}</Tag>} meta={survey ? `${survey.georef} · ${survey.accuracy?.check_rmse_h_m != null ? `check RMSE ${(survey.accuracy.check_rmse_h_m * 100).toFixed(1)} H / ${((survey.accuracy.check_rmse_v_m ?? 0) * 100).toFixed(1)} V cm · ` : ""}GSD ${survey.accuracy?.gsd_m != null ? (survey.accuracy.gsd_m * 100).toFixed(1) + " cm" : "—"} · ${counts.total} structures` : undefined} />
        <DockTabs tabs={["Structures", "Shots", "Measure", "Layers"]} active={tab} onPick={setTab} />
        {tab === "Structures" && (
          <>
            <div className="row" style={{ padding: "8px 14px", gap: 6 }}>
              {(["all", "pending", "mountable"] as const).map((f) => <button key={f} className={`tag ${filter === f ? "t-acc" : "t-mute"}`} style={{ border: "none", cursor: "pointer" }} onClick={() => setFilter(f)}>{f}{f === "pending" ? ` ${counts.pending}` : f === "all" ? ` ${counts.total}` : ""}</button>)}
            </div>
            <div className="scroll" style={{ flex: 1 }}>
              {structures.isLoading && <Empty title="Loading…" />}
              {list.map((s) => {
                const conf = s.confidence;
                const confc = conf >= 0.8 ? "#3ddc84" : conf >= 0.5 ? "#ffb347" : "#ff5c5c";
                const insufficient = (s.view_count != null && s.view_count < 20) || (s.accuracy_m != null && s.accuracy_m > 0.1);
                return (
                  <div key={s.id} onClick={() => ui.select(s.id)} className="row" style={{ gap: 8, padding: "6px 14px", borderBottom: "1px solid var(--color-line)", background: s.id === ui.selection ? "var(--color-acc-dim)" : "transparent", fontSize: 12, cursor: "pointer" }}>
                    <span style={{ width: 96, fontWeight: s.id === ui.selection ? 600 : 500, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{s.name}</span>
                    <span className="m" style={{ width: 62, color: "var(--color-ink-2)", fontSize: 11 }}>{s.cls}</span>
                    <Bar pct={conf * 100} color={confc} width={40} />
                    <span className="m" style={{ width: 30, fontSize: 11 }}>{conf.toFixed(2)}</span>
                    <span className={`tag t-${TONE[s.state] ?? "mute"}`} style={{ width: 62, justifyContent: "center" }}>{s.state}</span>
                    <span className="m" style={{ width: 40, textAlign: "right", fontSize: 11, color: "var(--color-ink-2)" }}>{s.accuracy_m != null ? `±${s.accuracy_m.toFixed(2)}` : ""}</span>
                    {insufficient && <Tag tone="warn">insuff.</Tag>}
                  </div>
                );
              })}
            </div>
            {selected && (
              <div style={{ borderTop: "1px solid var(--color-line)", padding: "12px 14px", display: "flex", flexDirection: "column", gap: 8 }}>
                <div className="row" style={{ justifyContent: "space-between" }}>
                  <div className="row"><span style={{ fontWeight: 700, fontSize: 14 }}>{selected.name}</span><Tag>{selected.cls}</Tag><Tag>{selected.origin}</Tag></div>
                  <span className="m" style={{ fontSize: 10.5, color: "var(--color-ink-3)" }}>{selected.point_count ?? "—"} pts · {selected.view_count ?? "—"} views</span>
                </div>
                <div style={{ display: "grid", gridTemplateColumns: "repeat(3, minmax(0,1fr))", gap: 6 }}>
                  <div><div className="lbl" style={{ fontSize: 9.5 }}>Height</div><div className="m" style={{ fontSize: 12 }}>{dims(selected).h}</div></div>
                  <div><div className="lbl" style={{ fontSize: 9.5 }}>Size</div><div className="m" style={{ fontSize: 12 }}>{dims(selected).w}</div></div>
                  <div><div className="lbl" style={{ fontSize: 9.5 }}>Mountable</div>
                    <button onClick={() => review(selected, { mountable: !selected.mountable })} className="row" style={{ gap: 6, background: "none", border: "none", color: "inherit", cursor: "pointer", padding: 0 }}>
                      <span style={{ width: 24, height: 14, borderRadius: 7, background: selected.mountable ? "var(--color-acc)" : "#2b3441", position: "relative", display: "inline-block" }}><span style={{ position: "absolute", top: 2, [selected.mountable ? "right" : "left"]: 2, width: 10, height: 10, borderRadius: "50%", background: selected.mountable ? "#06202a" : "#98a2b3" }} /></span>
                      <span style={{ fontSize: 12 }}>{selected.mountable ? "yes" : "no"}</span>
                    </button>
                  </div>
                </div>
                <Kv k="Porosity" v={selected.porosity?.toFixed(2) ?? "0.00"} />
                {selected.reject_reason && <Kv k="Rejected as" v={selected.reject_reason} mono={false} />}
                <div className="row" style={{ gap: 6, flexWrap: "wrap" }}>
                  <button className="btn acc" style={{ height: 26 }} onClick={() => review(selected, { state: "accepted" })}>Accept <span className="kbd" style={{ color: "#06202a", borderColor: "rgba(0,0,0,0.3)" }}>a</span></button>
                  {(["noise", "transient", "duplicate"] as const).map((r, i) => <button key={r} className="btn" style={{ height: 26 }} onClick={() => review(selected, { state: "rejected", reject_reason: r })}>Reject: {r} <span className="kbd">r {i + 1}</span></button>)}
                  <button className="btn" style={{ height: 26 }} onClick={() => review(selected, { state: "seasonal" })}>Seasonal <span className="kbd">s</span></button>
                  <select className="input" style={{ width: "auto", height: 26 }} value={selected.cls} onChange={(e) => review(selected, { cls: e.target.value })}>
                    {["pole", "fence", "building", "stand", "goal", "vegetation", "ground", "other"].map((c) => <option key={c} value={c}>{c}</option>)}
                  </select>
                </div>
                <div style={{ fontSize: 11, color: "var(--color-ink-3)" }}>Reclassifying refits the primitive with the new class's fitter. Only accepted structures occlude.</div>
              </div>
            )}
          </>
        )}
        {tab === "Shots" && <Empty title="Camera shots" hint="Solved camera poses arrive with reconstruction (M7)." />}
        {tab === "Measure" && <Empty title="Measure" hint="Snapping needs the point cloud and DSM (M9/M12). The API already refuses measurements on scale-free surveys." />}
        {tab === "Layers" && (
          <div style={{ padding: 14, display: "flex", flexDirection: "column", gap: 6 }}>
            {[["basemap", "Topographic basemap"], ["imagery", "Aerial imagery (Lands Department)"], ["labels", "Labels"], ["structures", "Structures (by review state)"]].map(([k, l]) => (
              <label key={k} className="row" style={{ gap: 8, fontSize: 12, cursor: "pointer" }}><input type="checkbox" checked={!!ui.layers[k!]} onChange={() => ui.toggleLayer(k!)} style={{ accentColor: "var(--color-acc)" }} />{l}</label>
            ))}
            <div className="hr" style={{ margin: "6px 0" }} />
            <div className="lbl">Review colours</div>
            {Object.entries(STATE_COLOR).map(([k, c]) => <div key={k} className="row" style={{ fontSize: 12 }}><span style={{ width: 10, height: 10, borderRadius: "50%", border: `2px solid ${c}`, display: "inline-block" }} />{k}</div>)}
          </div>
        )}
        <DockFooter>
          <span className="m" style={{ fontSize: 11, color: "var(--color-ink-3)" }}>{counts.pending} pending · occluders read state = accepted</span>
          {ctx.links.find((l) => l.stage === "Plan")?.to && <Link className="btn acc" style={{ marginLeft: "auto" }} to={ctx.links.find((l) => l.stage === "Plan")!.to!}>Plan →</Link>}
        </DockFooter>
      </Dock>
    </Shell>
  );
}

function dims(s: Structure): { h: string; w: string } {
  const p = s.primitive;
  const tol = s.fit_rmse_m != null ? ` ± ${Math.max(0.01, s.fit_rmse_m * 2).toFixed(2)}` : "";
  if (p.kind === "cylinder") return { h: `${(p.y1 - p.y0).toFixed(2)} m${tol}`, w: `r ${p.r.toFixed(2)} m` };
  if (p.kind === "box") return { h: `${(2 * p.hy).toFixed(2)} m${tol}`, w: `${(2 * p.hx).toFixed(1)} × ${(2 * p.hz).toFixed(1)} m` };
  let len = 0;
  for (let i = 0; i + 1 < p.points.length; i++) len += Math.hypot(p.points[i + 1]![0] - p.points[i]![0], p.points[i + 1]![1] - p.points[i]![1]);
  return { h: `${(p.y1 - p.y0).toFixed(2)} m${tol}`, w: `${len.toFixed(1)} m run` };
}
