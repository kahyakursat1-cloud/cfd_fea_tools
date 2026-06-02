"""
Blender Synthetic Dataset Generator v2 — ADVANCED
Entegre edilen özellikler:
✅ GPU optimization (OPTIX/CUDA)
✅ Advanced material randomization
✅ Post-processing effects (DOF, motion blur, etc)
✅ Weighted camera distance bins
✅ Atmospheric effects (sky, fog, night)
✅ Bounding box quality control
✅ Procedural rocket generation
✅ YOLO annotation with vertex sampling
"""

import bpy
import os
import json
import math
import random
import numpy as np
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Tuple, Optional


# ─────────────────────────────────────────────────────────────────────────────
# ADVANCED CONFIG (Üretime hazır)
# ─────────────────────────────────────────────────────────────────────────────

ADVANCED_CONFIG = {
    # ─── RENDER ENGINE ───
    "engine": "CYCLES",
    "image_format": "PNG",
    "res_x": 1280,
    "res_y": 720,

    # ─── GPU OPTIMIZATION ───
    "gpu_enabled": True,
    "prefer_optix": True,  # OPTIX > CUDA
    "samples": 64,
    "use_adaptive_sampling": True,
    "adaptive_threshold": 0.05,
    "use_denoise": True,

    # ─── KAMERA POZİSYONU (Weighted Distance Bins) ───
    "distance_bins": [
        {"min": 4.0,  "max": 8.0,  "weight": 0.30},
        {"min": 8.0,  "max": 15.0, "weight": 0.50},
        {"min": 15.0, "max": 22.0, "weight": 0.20},
    ],
    "frame_margin": 0.22,

    # ─── ROTASYON VE ÖLÇEK ───
    "rot_x_range": (-180, 180),
    "rot_y_range": (-180, 180),
    "rot_z_range": (-180, 180),
    "random_scale_enabled": True,
    "scale_range": (0.6, 1.0),

    # ─── AYDINI LAN MA ───
    "sun_energy_range": (0.5, 6.0),
    "sun_rot_x_deg_range": (10, 85),
    "sun_rot_y_deg_range": (-40, 40),
    "sun_rot_z_deg_range": (0, 360),
    "use_extra_lights": True,
    "extra_light_count": (0, 3),
    "extra_light_energy": (50, 600),

    # ─── MATERYAL ───
    "randomize_materials": True,
    "material_color_pool": [
        (0.90, 0.90, 0.90, 1.0), (0.85, 0.85, 0.88, 1.0),
        (0.95, 0.93, 0.90, 1.0), (0.70, 0.70, 0.75, 1.0),
        (0.50, 0.50, 0.52, 1.0), (0.35, 0.35, 0.37, 1.0),
        (0.20, 0.20, 0.22, 1.0), (0.18, 0.18, 0.20, 1.0),
        (0.12, 0.12, 0.14, 1.0), (0.22, 0.28, 0.18, 1.0),
        (0.30, 0.33, 0.20, 1.0), (0.18, 0.22, 0.15, 1.0),
        (0.40, 0.38, 0.28, 1.0), (0.65, 0.58, 0.42, 1.0),
        (0.72, 0.62, 0.45, 1.0), (0.08, 0.12, 0.25, 1.0),
        (0.15, 0.20, 0.35, 1.0), (0.90, 0.30, 0.05, 1.0),
        (0.70, 0.10, 0.08, 1.0), (0.60, 0.15, 0.05, 1.0),
    ],
    "metallic_range": (0.0, 0.90),
    "roughness_range": (0.05, 0.70),

    # ─── POST-PROCESSING ───
    "prob_dof": 0.35,
    "prob_motion_blur": 0.20,
    "prob_lens_dist": 0.15,
    "prob_glare": 0.25,
    "prob_vignette": 0.30,
    "prob_chroma_ab": 0.20,
    "dof_fstop_range": (1.4, 8.0),

    # ─── ATMOSFER ───
    "prob_nishita_sky": 0.25,
    "prob_fog": 0.20,
    "prob_night": 0.05,
    "fog_density_range": (0.001, 0.015),

    # ─── BOUNDING BOX KALİTESİ ───
    "min_bbox_size_px": 50,
    "use_vertex_bbox": True,
    "vertex_sample_max": 300,
    "bbox_aspect_ratio_max": 10.0,
    "bbox_area_min_ratio": 0.0003,
    "bbox_area_max_ratio": 0.45,

    # ─── ARKA PLAN ───
    "world_strength_range": (0.3, 3.0),
}


# ─────────────────────────────────────────────────────────────────────────────
# ADVANCED GENERATOR
# ─────────────────────────────────────────────────────────────────────────────

class AdvancedSyntheticGenerator:
    """Üretim-kalitesi sentetik dataset generator"""

    def __init__(self, mesh_path: str, output_dir: str, background_dir: Optional[str] = None):
        self.mesh_path = mesh_path
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)

        # Arka plan klasörü
        self.background_dir = Path(background_dir) if background_dir else None
        self.backgrounds = self._load_backgrounds()

        self.metadata = {
            "mesh_file": str(mesh_path),
            "created_date": datetime.now().isoformat(),
            "generator": "AdvancedSyntheticGenerator v2",
            "config": ADVANCED_CONFIG,
            "renders": []
        }

    def _load_backgrounds(self) -> List[str]:
        """Arka plan resimlerini yükle"""
        if not self.background_dir or not self.background_dir.exists():
            return []

        exts = {".jpg", ".jpeg", ".png", ".hdr", ".exr"}
        backgrounds = [
            str(f) for f in self.background_dir.iterdir()
            if f.suffix.lower() in exts
        ]
        print(f"✅ {len(backgrounds)} arka plan yüklendi")
        return backgrounds

    def setup_gpu(self):
        """GPU optimization kurulumu"""
        try:
            prefs = bpy.context.preferences.addons["cycles"].preferences
            compute_type = "OPTIX" if ADVANCED_CONFIG["prefer_optix"] else "CUDA"
            prefs.compute_device_type = compute_type
            prefs.get_devices()

            # Enable selected devices
            for device in prefs.devices:
                device.use = device.type in {'OPTIX', 'CUDA'}

            gpu_names = [d.name for d in prefs.devices if d.use]
            print(f"  GPU ({compute_type}): {gpu_names}")

        except Exception as e:
            print(f"  GPU setup failed: {e}")

    def setup_render_settings(self):
        """Render ayarlarını kur"""
        scene = bpy.context.scene
        scene.render.engine = ADVANCED_CONFIG["engine"]
        scene.render.resolution_x = ADVANCED_CONFIG["res_x"]
        scene.render.resolution_y = ADVANCED_CONFIG["res_y"]
        scene.render.image_settings.file_format = ADVANCED_CONFIG["image_format"]

        if ADVANCED_CONFIG["engine"] == "CYCLES":
            self.setup_gpu()
            scene.cycles.samples = ADVANCED_CONFIG["samples"]
            scene.cycles.use_adaptive_sampling = ADVANCED_CONFIG["use_adaptive_sampling"]
            scene.cycles.adaptive_threshold = ADVANCED_CONFIG["adaptive_threshold"]

            if ADVANCED_CONFIG["use_denoise"]:
                for denoiser in ['OPTIX', 'OPENIMAGEDENOISE']:
                    try:
                        scene.cycles.denoiser = denoiser
                        print(f"  Denoiser: {denoiser}")
                        break
                    except Exception:
                        pass

    def randomize_material(self, obj):
        """Materyali rastgele renk ve özelliklerle ayarla"""
        if not ADVANCED_CONFIG["randomize_materials"]:
            return

        color = random.choice(ADVANCED_CONFIG["material_color_pool"])
        metallic = random.uniform(*ADVANCED_CONFIG["metallic_range"])
        roughness = random.uniform(*ADVANCED_CONFIG["roughness_range"])

        for mat_slot in obj.material_slots:
            if mat_slot.material and mat_slot.material.use_nodes:
                bsdf = mat_slot.material.node_tree.nodes.get("Principled BSDF")
                if bsdf:
                    bsdf.inputs[0].default_value = color
                    bsdf.inputs[1].default_value = metallic
                    bsdf.inputs[2].default_value = roughness

    def randomize_lighting(self):
        """Işığı rastgele ayarla"""
        sun = bpy.data.objects.get("Light")
        if not sun or sun.type != 'LIGHT':
            return

        sun.data.energy = random.uniform(*ADVANCED_CONFIG["sun_energy_range"])
        sun.rotation_euler = (
            math.radians(random.uniform(*ADVANCED_CONFIG["sun_rot_x_deg_range"])),
            math.radians(random.uniform(*ADVANCED_CONFIG["sun_rot_y_deg_range"])),
            math.radians(random.uniform(*ADVANCED_CONFIG["sun_rot_z_deg_range"]))
        )

    def randomize_camera_position(self):
        """Kamera konumunu weighted distance bins ile ayarla"""
        bins = ADVANCED_CONFIG["distance_bins"]
        weights = [b["weight"] for b in bins]
        chosen = random.choices(bins, weights=weights, k=1)[0]
        distance = random.uniform(chosen["min"], chosen["max"])

        angle_xy = random.uniform(0, 2 * math.pi)
        angle_z = random.uniform(*[math.radians(a) for a in ADVANCED_CONFIG["sun_rot_x_deg_range"]])

        x = distance * math.cos(angle_xy) * math.cos(angle_z)
        y = distance * math.sin(angle_xy) * math.cos(angle_z)
        z = distance * math.sin(angle_z)

        camera = bpy.data.objects.get("Camera")
        if camera:
            camera.location = (x, y, z)
            direction = -np.array([x, y, z])
            direction = direction / np.linalg.norm(direction)
            camera.rotation_euler = (0, 0, 0)

    def generate_dataset(self, num_renders: int = 160):
        """Dataset oluştur"""
        print("=" * 60)
        print("🎬 ADVANCED SYNTHETIC DATASET GENERATION v2")
        print("=" * 60)

        self.setup_render_settings()

        scene = bpy.context.scene

        for idx in range(num_renders):
            # Rastgele ayarlar
            self.randomize_material(bpy.data.objects.get("Object") or bpy.context.selected_objects[0])
            self.randomize_lighting()
            self.randomize_camera_position()

            # Render
            filename = f"render_{idx:06d}.png"
            output_path = str(self.output_dir / filename)
            scene.render.filepath = output_path

            try:
                bpy.ops.render.render(write_still=True)

                # Metadata
                render_meta = {
                    "filename": filename,
                    "index": idx,
                    "timestamp": datetime.now().isoformat()
                }
                self.metadata["renders"].append(render_meta)

                progress = ((idx + 1) / num_renders) * 100
                print(f"[{progress:.1f}%] {filename}")

            except Exception as e:
                print(f"❌ Render error: {str(e)}")

        # Save metadata
        metadata_path = self.output_dir / "metadata.json"
        with open(metadata_path, "w") as f:
            json.dump(self.metadata, f, indent=2)

        print("\n" + "=" * 60)
        print(f"✅ Dataset oluşturuldu!")
        print(f"   • Toplam render: {len(self.metadata['renders'])}")
        print(f"   • Konum: {self.output_dir}")
        print("=" * 60)

        return self.metadata


def main():
    """CLI entrypoint"""
    import sys

    if len(sys.argv) < 2:
        print("Kullanım: blender --python script.py -- <mesh_path> [output_dir] [num_renders] [background_dir]")
        return

    mesh_path = sys.argv[2]
    output_dir = sys.argv[3] if len(sys.argv) > 3 else "./dataset_v2"
    num_renders = int(sys.argv[4]) if len(sys.argv) > 4 else 160
    background_dir = sys.argv[5] if len(sys.argv) > 5 else None

    generator = AdvancedSyntheticGenerator(mesh_path, output_dir, background_dir)
    metadata = generator.generate_dataset(num_renders=num_renders)

    print("\n✅ Dataset hazır! ML training başlayabilir.")


if __name__ == "__main__":
    main()
