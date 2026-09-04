/* The 3D view: the same layers as the plan, in local ENU (Y up). Terrain is a
 * flat plane until M9 ships the terrain grid; the point cloud and mesh tiles
 * arrive with M9 too. Coverage is a texture on the ground plane. */

import { OrbitControls } from "@react-three/drei";
import { Canvas } from "@react-three/fiber";
import { useEffect, useMemo, useRef } from "react";
import * as THREE from "three";
import type { CameraSpec, Structure } from "../api/contracts";
import { hfovRad, vfovRad } from "../kernel/optics";
import { primitiveRing, STATE_COLOR } from "../map/features";

export interface Scene3DProps {
  extent: { x_min: number; x_max: number; z_min: number; z_max: number };
  structures: Structure[];
  cameras: CameraSpec[];
  selected: string | null;
  heatCanvas?: HTMLCanvasElement | null;
  heatExtent?: { x_min: number; x_max: number; z_min: number; z_max: number } | null;
  onSelect?: (id: string | null) => void;
}

function Ground({ extent, heatCanvas, heatExtent }: Pick<Scene3DProps, "extent" | "heatCanvas" | "heatExtent">) {
  const w = extent.x_max - extent.x_min, d = extent.z_max - extent.z_min;
  const tex = useMemo(() => {
    if (!heatCanvas) return null;
    const t = new THREE.CanvasTexture(heatCanvas);
    t.magFilter = THREE.NearestFilter;
    t.minFilter = THREE.NearestFilter;
    t.colorSpace = THREE.SRGBColorSpace;
    return t;
  }, [heatCanvas]);
  useEffect(() => () => tex?.dispose(), [tex]);
  return (
    <group>
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[extent.x_min + w / 2, -0.02, extent.z_min + d / 2]}>
        <planeGeometry args={[w, d]} />
        <meshStandardMaterial color="#2f4726" />
      </mesh>
      {tex && heatExtent && (
        <mesh rotation={[-Math.PI / 2, 0, 0]} position={[(heatExtent.x_min + heatExtent.x_max) / 2, 0.02, (heatExtent.z_min + heatExtent.z_max) / 2]}>
          <planeGeometry args={[heatExtent.x_max - heatExtent.x_min, heatExtent.z_max - heatExtent.z_min]} />
          <meshBasicMaterial map={tex} transparent opacity={0.92} side={THREE.DoubleSide} />
        </mesh>
      )}
      <gridHelper args={[Math.max(w, d) * 2, Math.round(Math.max(w, d) / 5), "#1c2430", "#151a21"]} position={[extent.x_min + w / 2, -0.03, extent.z_min + d / 2]} />
    </group>
  );
}

function Primitives({ structures, selected, onSelect }: Pick<Scene3DProps, "structures" | "selected" | "onSelect">) {
  return (
    <group>
      {structures.map((s) => {
        const p = s.primitive;
        const state = s.origin === "manual" && s.name.startsWith("proposed") ? "proposed" : s.state;
        const color = STATE_COLOR[state] ?? "#98a2b3";
        const isSel = s.id === selected;
        const mat = <meshStandardMaterial color={color} transparent opacity={s.state === "rejected" ? 0.25 : isSel ? 0.9 : 0.55} wireframe={s.state === "rejected"} />;
        const click = (e: { stopPropagation: () => void }) => { e.stopPropagation(); onSelect?.(s.id); };
        if (p.kind === "cylinder") {
          const h = p.y1 - p.y0;
          return (
            <mesh key={s.id} position={[p.cx, p.y0 + h / 2, p.cz]} onClick={click}>
              <cylinderGeometry args={[Math.max(p.r, 0.15), Math.max(p.r, 0.15), h, 16]} />
              {mat}
            </mesh>
          );
        }
        if (p.kind === "box") {
          return (
            <mesh key={s.id} position={[p.cx, p.cy, p.cz]} rotation={[0, p.yaw ?? 0, 0]} onClick={click}>
              <boxGeometry args={[p.hx * 2, p.hy * 2, p.hz * 2]} />
              {mat}
            </mesh>
          );
        }
        // polyline: one thin box per segment
        const ring = primitiveRing(p);
        void ring;
        return (
          <group key={s.id} onClick={click}>
            {p.points.slice(0, -1).map(([x1, z1], i) => {
              const [x2, z2] = p.points[i + 1]!;
              const len = Math.hypot(x2 - x1, z2 - z1);
              const yaw = Math.atan2(-(z2 - z1), x2 - x1);
              return (
                <mesh key={i} position={[(x1 + x2) / 2, (p.y0 + p.y1) / 2, (z1 + z2) / 2]} rotation={[0, yaw, 0]}>
                  <boxGeometry args={[len, p.y1 - p.y0, Math.max(p.thickness, 0.12)]} />
                  {mat}
                </mesh>
              );
            })}
          </group>
        );
      })}
    </group>
  );
}

function Frusta({ cameras, selected, onSelect }: Pick<Scene3DProps, "cameras" | "selected" | "onSelect">) {
  return (
    <group>
      {cameras.map((c) => {
        const far = 40;
        const th = Math.tan(hfovRad(c.sensor_w_mm, c.focal_mm) / 2), tv = Math.tan(vfovRad(c.sensor_h_mm, c.focal_mm) / 2);
        const pan = (c.pan_deg * Math.PI) / 180, tilt = (c.tilt_deg * Math.PI) / 180;
        const f = new THREE.Vector3(Math.sin(pan) * Math.cos(tilt), -Math.sin(tilt), -Math.cos(pan) * Math.cos(tilt));
        const r = new THREE.Vector3().crossVectors(f, new THREE.Vector3(0, 1, 0)).normalize();
        const u = new THREE.Vector3().crossVectors(r, f).normalize();
        const o = new THREE.Vector3(c.position.x, c.position.y, c.position.z);
        const corners = [[-1, -1], [1, -1], [1, 1], [-1, 1]].map(([sx, sy]) => o.clone().add(f.clone().multiplyScalar(far)).add(r.clone().multiplyScalar(sx! * far * th)).add(u.clone().multiplyScalar(sy! * far * tv)));
        const pts: THREE.Vector3[] = [];
        for (const k of corners) pts.push(o, k);
        for (let i = 0; i < 4; i++) pts.push(corners[i]!, corners[(i + 1) % 4]!);
        const geom = new THREE.BufferGeometry().setFromPoints(pts);
        const isSel = c.id === selected;
        const color = c.enabled === false ? "#3a4656" : isSel ? "#ffb347" : "#5ee7ff";
        return (
          <group key={c.id}>
            <lineSegments geometry={geom}><lineBasicMaterial color={color} transparent opacity={isSel ? 1 : 0.6} /></lineSegments>
            <mesh position={o} onClick={(e) => { e.stopPropagation(); onSelect?.(c.id); }}>
              <sphereGeometry args={[0.5, 12, 12]} />
              <meshStandardMaterial color={color} />
            </mesh>
          </group>
        );
      })}
    </group>
  );
}

export function Scene3D(props: Scene3DProps) {
  const { extent } = props;
  const cx = (extent.x_min + extent.x_max) / 2, cz = (extent.z_min + extent.z_max) / 2;
  const span = Math.max(extent.x_max - extent.x_min, extent.z_max - extent.z_min);
  const controls = useRef<never>(null);
  return (
    <Canvas camera={{ position: [cx + span * 0.55, span * 0.6, cz + span * 0.75], fov: 45, near: 0.5, far: 5000 }} style={{ position: "absolute", inset: 0, background: "#0b0e13" }} onPointerMissed={() => props.onSelect?.(null)}>
      <ambientLight intensity={0.7} />
      <directionalLight position={[100, 200, 50]} intensity={0.9} />
      <Ground extent={extent} heatCanvas={props.heatCanvas} heatExtent={props.heatExtent} />
      <Primitives structures={props.structures} selected={props.selected} onSelect={props.onSelect} />
      <Frusta cameras={props.cameras} selected={props.selected} onSelect={props.onSelect} />
      <OrbitControls ref={controls} target={[cx, 0, cz]} maxPolarAngle={Math.PI / 2 - 0.02} />
    </Canvas>
  );
}
