/* The site: surveys and scenarios over the site map. Entry to the stages.
 *
 * The outlines drawn here are the facility polygons, but they are presented as the
 * site's own extent rather than as a separate level the operator has to navigate. */

import { useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useFacilities, useScenarios, useSurveys, useVenue } from "../api/queries";
import { Shell } from "../app/Shell";
import { Dock, DockHeader, DockTabs, Empty, Tag } from "../components/ui";
import { localToLngLat, storageRingToLngLat } from "../geo";
import { GeoLayer, MapView } from "../map/MapView";
import { STATUS_TONE } from "./useStageContext";

export function VenuePage() {
  const { venueId } = useParams();
  const venue = useVenue(venueId);
  const facilities = useFacilities(venueId);
  const surveys = useSurveys(venueId);
  const scenarios = useScenarios(venueId);
  const [tab, setTab] = useState("Surveys");
  const v = venue.data;
  const fc = useMemo<GeoJSON.FeatureCollection>(() => ({
    type: "FeatureCollection",
    features: v ? (facilities.data ?? []).map((f) => ({ type: "Feature", id: f.id, properties: { name: f.name }, geometry: { type: "Polygon", coordinates: [storageRingToLngLat(v.srid, f.boundary)] } })) : [],
  }), [v, facilities.data]);
  // Labels on their own point source: a polygon label is placed once per tile
  // the polygon crosses, so "Main pitch" would appear twice at the tile seam.
  const labels = useMemo<GeoJSON.FeatureCollection>(() => ({
    type: "FeatureCollection",
    features: fc.features.map((f) => {
      const ring = (f.geometry as GeoJSON.Polygon).coordinates[0]!.slice(0, -1);
      const c = ring.reduce<[number, number]>((a, p) => [a[0] + p[0]! / ring.length, a[1] + p[1]! / ring.length], [0, 0]);
      return { type: "Feature", id: f.id, properties: f.properties, geometry: { type: "Point", coordinates: c } };
    }),
  }), [fc]);
  const center: [number, number] = v ? localToLngLat(v, 0, 0) : [114.17, 22.32];
  const bounds = useMemo(() => (v && facilities.data?.[0] ? storageRingToLngLat(v.srid, facilities.data[0].boundary) : null), [v, facilities.data]);
  const latest = surveys.data?.find((s) => s.status === "complete");
  return (
    <Shell crumb={v?.name ?? "…"}>
      <MapView center={center} zoom={17} bounds={bounds}>
        <GeoLayer id="facilities" data={fc} layers={[
          { id: "fac-fill", type: "fill", paint: { "fill-color": "#5ee7ff", "fill-opacity": 0.08 } },
          { id: "fac-line", type: "line", paint: { "line-color": "#5ee7ff", "line-width": 1.5, "line-dasharray": [4, 3] } },
        ]} />
        <GeoLayer id="facility-labels" data={labels} layers={[
          { id: "fac-lbl", type: "symbol", layout: { "text-field": ["get", "name"], "text-size": 11.5 }, paint: { "text-color": "#e8ecf1", "text-halo-color": "#0e1116", "text-halo-width": 1.2 } },
        ]} />
      </MapView>
      <Dock>
        <DockHeader eyebrow="Site" title={v?.name ?? "…"} meta={v ? `${v.reference ?? ""} · EPSG:${v.srid} · origin ${v.origin_x.toFixed(0)} / ${v.origin_y.toFixed(0)} · ${v.height_datum}` : undefined} />
        <DockTabs tabs={["Surveys", "Scenarios"]} active={tab} onPick={setTab} />
        <div className="scroll" style={{ flex: 1 }}>
          {tab === "Surveys" && (surveys.data?.length ? surveys.data.map((s) => (
            <Link key={s.id} to={`/venues/${venueId}/surveys/${s.id}/${s.status === "complete" ? "model" : s.status === "draft" || s.status === "qa_review" ? "capture" : "process"}`} style={{ display: "block", color: "inherit", padding: "9px 14px", borderBottom: "1px solid var(--color-line)" }}>
              <div className="row" style={{ justifyContent: "space-between" }}><span style={{ fontWeight: 600 }}>{s.name}</span><Tag tone={STATUS_TONE[s.status] ?? "mute"}>{s.status.replace("_", " ")}</Tag></div>
              <div className="m" style={{ fontSize: 11, color: "var(--color-ink-2)", marginTop: 3 }}>{s.flown_at ?? "not flown"} · {s.georef} · {s.engine ?? "—"}{s.accuracy?.check_rmse_h_m != null ? ` · check RMSE ${(s.accuracy.check_rmse_h_m * 100).toFixed(1)} H / ${((s.accuracy.check_rmse_v_m ?? 0) * 100).toFixed(1)} V cm` : ""}</div>
            </Link>
          )) : <Empty title="No surveys" hint="Upload a flight to start the pipeline." />)}
          {tab === "Scenarios" && (scenarios.data?.length ? scenarios.data.map((sc) => (
            <Link key={sc.id} to={`/venues/${venueId}/scenarios/${sc.id}/plan`} style={{ display: "block", color: "inherit", padding: "9px 14px", borderBottom: "1px solid var(--color-line)" }}>
              <div style={{ fontWeight: 600 }}>{sc.name}</div>
              <div className="m" style={{ fontSize: 11, color: "var(--color-ink-2)", marginTop: 3 }}>{sc.cameras.length} cameras · {sc.tents.length} tents · seasonal {sc.include_seasonal ? "on" : "off"}</div>
            </Link>
          )) : <Empty title="No scenarios" hint={latest ? "Open the Model stage of the complete survey and press Plan." : "Complete a survey first."} />)}
        </div>
      </Dock>
    </Shell>
  );
}
