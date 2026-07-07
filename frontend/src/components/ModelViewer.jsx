import { useEffect, useRef, useState, Suspense } from "react";
import { Canvas, useThree } from "@react-three/fiber";
import { OrbitControls, GizmoHelper, GizmoViewport, Html } from "@react-three/drei";
import * as THREE from "three";
import { STLLoader } from "three/examples/jsm/loaders/STLLoader.js";
import { OBJLoader } from "three/examples/jsm/loaders/OBJLoader.js";
import { PLYLoader } from "three/examples/jsm/loaders/PLYLoader.js";
import { GLTFLoader } from "three/examples/jsm/loaders/GLTFLoader.js";
import { ColladaLoader } from "three/examples/jsm/loaders/ColladaLoader.js";
import { FBXLoader } from "three/examples/jsm/loaders/FBXLoader.js";
import { ThreeMFLoader } from "three/examples/jsm/loaders/3MFLoader.js";

// Generic model loader supporting multiple formats
function Model({ url, onReady, format }) {
  const [geometry, setGeometry] = useState(null);
  const [error, setError] = useState(null);
  const cbRef = useRef(onReady);
  cbRef.current = onReady;

  useEffect(() => {
    let cancelled = false;
    setGeometry(null);
    setError(null);

    const ext = format || url.split(".").pop()?.toLowerCase() || "";
    let loader;

    switch (ext) {
      case "stl":
        loader = new STLLoader();
        break;
      case "obj":
        loader = new OBJLoader();
        break;
      case "ply":
        loader = new PLYLoader();
        break;
      case "gltf":
      case "glb":
        loader = new GLTFLoader();
        break;
      case "dae":
        loader = new ColladaLoader();
        break;
      case "fbx":
        loader = new FBXLoader();
        break;
      case "3mf":
        loader = new ThreeMFLoader();
        break;
      default:
        setError(`Format non supporté: ${ext}`);
        return;
    }

    const extractGeometry = (data) => {
      // data can be: BufferGeometry (STL, PLY), Group/Object3D (OBJ, FBX, DAE), or GLTF result
      let geo;

      if (data.isBufferGeometry) {
        // Direct geometry (STL, PLY)
        geo = data;
      } else if (data.geometry) {
        // Single mesh with geometry
        geo = data.geometry;
      } else if (data.isGroup || data.isObject3D) {
        // Group/Object3D (OBJ, FBX, DAE) - find first mesh geometry
        data.traverse((child) => {
          if (child.isMesh && child.geometry && !geo) {
            geo = child.geometry;
          }
        });
      } else if (data.scene) {
        // GLTF/GLB/Collada result with scene
        data.scene.traverse((child) => {
          if (child.isMesh && child.geometry && !geo) {
            geo = child.geometry;
          }
        });
      } else if (data.scenes && data.scenes.length) {
        // GLTF with scenes array
        data.scenes[0].traverse((child) => {
          if (child.isMesh && child.geometry && !geo) {
            geo = child.geometry;
          }
        });
      }

      return geo;
    };

    const load = (data) => {
      if (cancelled) return;

      const geo = extractGeometry(data);

      if (!geo) {
        setError("Aucune géométrie trouvée dans le fichier.");
        return;
      }

      geo.computeVertexNormals();

      // Bounding box for info + normalization
      const box = new THREE.Box3().setFromBufferAttribute(geo.attributes.position);
      const size = new THREE.Vector3();
      box.getSize(size);

      // Bake centering + normalization so longest side == 4 units
      geo.center();
      const maxDim = Math.max(size.x, size.y, size.z) || 1;
      const scale = 4 / maxDim;
      geo.scale(scale, scale, scale);

      geo.computeBoundingSphere();
      const radius = geo.boundingSphere?.radius || 2;

      setGeometry(geo);
      cbRef.current?.({
        triangles: geo.attributes.position.count / 3,
        size,
        radius,
      });
    };

    const onError = (err) => {
      if (cancelled) return;
      console.error(`${ext.toUpperCase()} load error`, err);
      setError(`Impossible de charger ce fichier ${ext.toUpperCase()}.`);
    };

    loader.load(url, load, undefined, onError);

    return () => {
      cancelled = true;
    };
  }, [url, format]);

  if (error) {
    // Render error as HTML overlay (not inside Canvas)
    return (
      <Html fullscreen>
        <div style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          height: "100%",
          background: "var(--bg)",
          color: "var(--text)",
          padding: "20px",
          textAlign: "center",
        }}>
          <p>{error}</p>
        </div>
      </Html>
    );
  }
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

function CameraRig({ radius }) {
  const camera = useThree((s) => s.camera);
  const controls = useThree((s) => s.controls);

  useEffect(() => {
    if (!radius) return;
    const fov = (camera.fov || 45) * THREE.MathUtils.DEG2RAD;
    const dist = (radius / Math.sin(fov / 2)) * 1.12;
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

export default function ModelViewer({ url, onLoaded, format }) {
  const [info, setInfo] = useState(null);

  const handleReady = (d) => {
    setInfo(d);
    onLoaded?.(d);
  };

  return (
    <Canvas camera={{ position: [6, 5, 8], fov: 45 }} style={{ background: "var(--bg)" }}>
      <ambientLight intensity={0.5} />
      <directionalLight position={[10, 10, 5]} intensity={1.2} />
      <directionalLight position={[-8, -5, -8]} intensity={0.4} color="#4aa8ff" />
      <Suspense fallback={null}>
        <Model url={url} onReady={handleReady} format={format} />
      </Suspense>
      <CameraRig radius={info?.radius} />
      <OrbitControls makeDefault enableDamping dampingFactor={0.1} />
      <GizmoHelper alignment="bottom-right" margin={[70, 70]}>
        <GizmoViewport axisColors={["#ff5c5c", "#4cd07a", "#4aa8ff"]} labelColor="white" />
      </GizmoHelper>
    </Canvas>
  );
}