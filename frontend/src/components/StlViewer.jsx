import { useEffect, useRef, useState, Suspense } from "react";
import { Canvas, useThree } from "@react-three/fiber";
import { OrbitControls, GizmoHelper, GizmoViewport } from "@react-three/drei";
import * as THREE from "three";
import { STLLoader } from "three/examples/jsm/loaders/STLLoader.js";

// Loads an STL from a URL and renders it centered + auto-scaled.
//
// The centering + normalization are BAKED INTO THE GEOMETRY (geo.center() +
// geo.scale()), not applied to the mesh. A previous version moved
// `meshRef.current`, but that ref is null until the next React commit — i.e. at
// the moment the loader callback runs the mesh doesn't exist yet — so the
// centering silently never applied and the model ended up floating in space,
// off-camera. Baking the transform into the geometry makes the model appear
// already framed at the origin on first render.
function StlModel({ url, onReady }) {
  const [geometry, setGeometry] = useState(null);
  const [error, setError] = useState(null);
  // Keep the callback in a ref so the load effect only depends on `url` —
  // otherwise a new closure each render would retrigger the STL download.
  const cbRef = useRef(onReady);
  cbRef.current = onReady;

  useEffect(() => {
    let cancelled = false;
    setGeometry(null);
    setError(null);
    const loader = new STLLoader();
    loader.load(
      url,
      (geo) => {
        if (cancelled) return;
        geo.computeVertexNormals();

        // Original bounding box (for info + to compute the normalizer).
        const box = new THREE.Box3().setFromBufferAttribute(geo.attributes.position);
        const size = new THREE.Vector3();
        box.getSize(size);

        // Bake centering + normalization so longest side == 4 units.
        geo.center();
        const maxDim = Math.max(size.x, size.y, size.z) || 1;
        const scale = 4 / maxDim;
        geo.scale(scale, scale, scale);

        // True bounding sphere radius AFTER transform → used to frame the camera.
        geo.computeBoundingSphere();
        const radius = geo.boundingSphere ? geo.boundingSphere.radius : 2;

        setGeometry(geo);
        cbRef.current?.({
          triangles: geo.attributes.position.count / 3,
          size,
          radius,
        });
      },
      undefined,
      (err) => {
        if (cancelled) return;
        console.error("STL load error", err);
        setError("Impossible de charger ce fichier STL.");
      }
    );
    return () => {
      cancelled = true;
    };
  }, [url]);

  if (error) return <div className="empty"><p>{error}</p></div>;
  if (!geometry) return null;

  return (
    <mesh geometry={geometry}>
      <meshStandardMaterial
        color="#ff8c2a"
        metalness={0.15}
        roughness={0.6}
        flatShading={false}
      />
    </mesh>
  );
}

// Positions the camera so the loaded model fully fits the view, and points
// OrbitControls at the model center (the origin, since the geometry is baked
// centered). Re-runs whenever a new model's bounding radius arrives.
function CameraRig({ radius }) {
  const camera = useThree((s) => s.camera);
  const controls = useThree((s) => s.controls);

  useEffect(() => {
    if (!radius) return;
    // Distance at which a sphere of `radius` fits the vertical FOV, plus a
    // 12% margin so no limb touches the edge.
    const fov = (camera.fov || 45) * THREE.MathUtils.DEG2RAD;
    const dist = (radius / Math.sin(fov / 2)) * 1.12;
    // Classic 3/4 isometric-ish viewing angle, normalized to `dist`.
    const dir = new THREE.Vector3(0.6, 0.5, 0.8).normalize();
    camera.position.copy(dir.multiplyScalar(dist));
    camera.near = dist / 100;
    camera.far = dist * 100;
    camera.lookAt(0, 0, 0);
    camera.updateProjectionMatrix();

    if (controls) {
      controls.target.set(0, 0, 0);
      controls.update();
    }
  }, [radius, camera, controls]);

  return null;
}

export default function StlViewer({ url, onLoaded }) {
  const [info, setInfo] = useState(null);
  const handleReady = (d) => {
    setInfo(d);
    onLoaded?.(d);
  };

  return (
    <Canvas
      camera={{ position: [6, 5, 8], fov: 45 }}
      style={{ background: "var(--bg)" }}
    >
      <ambientLight intensity={0.5} />
      <directionalLight position={[10, 10, 5]} intensity={1.2} />
      <directionalLight position={[-8, -5, -8]} intensity={0.4} color="#4aa8ff" />
      <Suspense fallback={null}>
        <StlModel url={url} onReady={handleReady} />
      </Suspense>
      <CameraRig radius={info?.radius} />
      <OrbitControls makeDefault enableDamping dampingFactor={0.1} />
      <GizmoHelper alignment="bottom-right" margin={[70, 70]}>
        <GizmoViewport axisColors={["#ff5c5c", "#4cd07a", "#4aa8ff"]} labelColor="white" />
      </GizmoHelper>
    </Canvas>
  );
}
