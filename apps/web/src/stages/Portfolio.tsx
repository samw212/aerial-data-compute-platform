/* Every site on the map, each against its coverage target.
 *
 * A site is one thing here. The database still separates a venue from the
 * facilities inside it, because a ground can hold two pitches with different
 * targets, but the operator thinks in sites and the list says "site". Where a
 * venue holds several facilities the row reports the worst of them, since the
 * weakest facility is what governs whether the site is acceptable. */

import { useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import type { FacilityHealth, VenueSummary } from "../api/contracts";
import { useMe, usePortfolio } from "../api/queries";
import { Shell } from "../app/Shell";
import { Bar, Chips, Dock, DockFooter, DockHeader, Empty, Hud, Tag } from "../components/ui";
import { GeoLayer, MapView } from "../map/MapView";
import { useUi } from "../state/ui";

/** The facility that governs the site: lowest measured coverage, unmeasured last. */
function governing(v: VenueSummary): FacilityHealth | undefined {
  const measured = v.health.filter((h) => h.latest_pct != null);
  if (measured.length === 0) return v.health[0];
  return measured.reduce((a, b) => ((b.latest_pct ?? 0) < (a.latest_pct ?? 0) ? b : a));
}

export function Portfolio() {
  const me = useMe();
  const portfolio = usePortfolio(me.data?.org_id);
  const nav = useNavigate();
  const layers = useUi((s) => s.layers);
  const toggle = useUi((s) => s.toggleLayer);
  const [cursor, setCursor] = useState<[number, number] | null>(null);

  const sites = useMemo(() => portfolio.data ?? [], [portfolio.data]);
  const fc = useMemo<GeoJSON.FeatureCollection>(() => ({
    type: "FeatureCollection",
    features: sites.filter((v) => v.venue.centroid_lon != null).map((v) => {
      const below = v.health.some((h) => h.meets_target === false) || v.stale;
      const none = v.health.every((h) => h.latest_pct == null);
      return { type: "Feature", id: v.venue.id, properties: { id: v.venue.id, name: v.venue.name, color: none ? "#667085" : below ? "#ffb347" : "#3ddc84" }, geometry: { type: "Point", coordinates: [v.venue.centroid_lon!, v.venue.centroid_lat!] } };
    }),
  }), [sites]);
  const center = useMemo<[number, number]>(() => {
    const f = fc.features[0]?.geometry as GeoJSON.Point | undefined;
    return f ? [f.coordinates[0]!, f.coordinates[1]!] : [114.17, 22.32];
  }, [fc]);

  const rows = useMemo(
    () => [...sites].sort((a, b) => {
      const ga = governing(a), gb = governing(b);
      return Number(ga?.meets_target === true) - Number(gb?.meets_target === true)
        || (ga?.latest_pct ?? 0) - (gb?.latest_pct ?? 0);
    }),
    [sites],
  );

  return (
    <Shell crumb="Portfolio" jobs="○ idle">
      <MapView center={center} zoom={sites.length > 1 ? 11 : 16} onMouseMove={setCursor} onClick={(_, e) => {
        const f = e.target.queryRenderedFeatures(e.point, { layers: ["venue-pts"] })[0];
        if (f) nav(`/venues/${f.properties.id}`);
      }}>
        <GeoLayer id="venues" data={fc} layers={[
          { id: "venue-halo", type: "circle", paint: { "circle-radius": 16, "circle-color": ["get", "color"], "circle-opacity": 0.18 } },
          { id: "venue-pts", type: "circle", paint: { "circle-radius": 6, "circle-color": ["get", "color"], "circle-stroke-color": "#0e1116", "circle-stroke-width": 2 } },
          { id: "venue-lbl", type: "symbol", layout: { "text-field": ["get", "name"], "text-offset": [1.2, 0], "text-anchor": "left", "text-size": 11.5 }, paint: { "text-color": "#e8ecf1", "text-halo-color": "#0e1116", "text-halo-width": 1.2 } },
        ]} />
      </MapView>
      <Chips left={12} items={[
        { key: "basemap", label: "Topographic", on: layers.basemap ?? true, onToggle: () => toggle("basemap") },
        { key: "imagery", label: "Aerial imagery", on: layers.imagery ?? false, onToggle: () => toggle("imagery") },
        { key: "labels", label: "Labels", on: layers.labels ?? true, onToggle: () => toggle("labels") },
      ]} />
      <Hud lines={[cursor ? `${cursor[1].toFixed(5)}° N · ${cursor[0].toFixed(5)}° E` : "—", `${sites.length} ${sites.length === 1 ? "site" : "sites"}`]} />
      <Dock>
        <DockHeader eyebrow="Portfolio" title={sites[0]?.venue.org_id ? "EMSD MunSD" : "…"} />
        <div className="scroll" style={{ flex: 1 }}>
          {portfolio.isLoading && <Empty title="Loading…" />}
          {!portfolio.isLoading && rows.length === 0 && <Empty title="No sites yet" hint="Create one, or run `groma seed` for the sample site." />}
          {rows.map((v) => {
            const h = governing(v);
            return (
              <Link key={v.venue.id} to={`/venues/${v.venue.id}`} style={{ display: "block", color: "inherit", padding: "9px 14px", borderBottom: "1px solid var(--color-line)" }}>
                <div className="row" style={{ justifyContent: "space-between" }}>
                  <span style={{ fontWeight: 600 }}>{v.venue.name}</span>
                  {v.stale ? <Tag tone="warn">stale</Tag> : h?.latest_pct == null ? <Tag>no run</Tag> : null}
                </div>
                <div className="row" style={{ justifyContent: "space-between", marginTop: 4 }}>
                  <span style={{ color: "var(--color-ink-2)", fontSize: 12 }}>target <span className="m">{h?.target_tier ?? "—"}</span></span>
                  {h?.latest_pct != null ? (
                    <span className="row" style={{ gap: 6 }}><span className="m" style={{ fontSize: 12 }}>{h.latest_pct.toFixed(1)}%</span><Bar pct={h.latest_pct} color={h.meets_target ? "#3ddc84" : "#ffb347"} width={70} /><span className="m" style={{ fontSize: 10.5, color: "var(--color-ink-3)" }}>/{h.target_pct}</span></span>
                  ) : <span style={{ color: "var(--color-ink-3)", fontSize: 12 }}>no run</span>}
                </div>
                <div className="m" style={{ fontSize: 10.5, color: "var(--color-ink-3)", marginTop: 3 }}>survey {h?.last_survey_flown_at ?? v.latest_survey_flown_at ?? "—"}</div>
              </Link>
            );
          })}
        </div>
        <DockFooter><span className="btn" title="Arrives with the site editor">New site</span><a className="btn" href={`/api/orgs/${me.data?.org_id}/coverage-health`} target="_blank" rel="noreferrer">Health JSON</a></DockFooter>
      </Dock>
    </Shell>
  );
}
