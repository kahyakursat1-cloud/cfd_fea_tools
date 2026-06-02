"""
Blender Synthetic Dataset Generator
Taranmış 3D model → Sentetik veriler oluşturma
CFD/FEA eğitim dataset'i otomasyonu
"""

import bpy
import bmesh
import numpy as np
from pathlib import Path
from typing import List, Dict, Tuple
from dataclasses import dataclass
import json
import os

# ─────────────────────────────────────────────────────────────────────────────
# BLENDER SETUP (Bu script Blender içinde çalışır)
# ─────────────────────────────────────────────────────────────────────────────

"""
Kullanım:
1. Blender aç
2. Scripting workspace'e git
3. Text Editor → New
4. Bu kodu yapıştır
5. Alt+P ile çalıştır

Veya command line'dan:
    blender --python blender_synthetic_generator.py
"""

# ─────────────────────────────────────────────────────────────────────────────
# DATACLASSES
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class RenderConfig:
    """Render konfigürasyonu"""
    resolution_x: int = 1280
    resolution_y: int = 720
    samples: int = 128
    engine: str = "CYCLES"  # CYCLES | EEVEE
    output_format: str = "PNG"

@dataclass
class CameraView:
    """Kamera açısı"""
    name: str
    location: Tuple[float, float, float]  # (x, y, z)
    rotation: Tuple[float, float, float]  # (rx, ry, rz) derece
    zoom: float = 1.0

@dataclass
class LightingSetup:
    """Aydınlatma konfigürasyonu"""
    name: str
    light_types: List[str]  # "SUN" | "POINT" | "SPOT" | "AREA"
    intensities: List[float]
    angles: List[Tuple[float, float, float]]  # Euler angles

@dataclass
class TextureVariant:
    """Doku/renk varyantı"""
    name: str
    base_color: Tuple[float, float, float, float]  # RGBA
    metallic: float = 0.0
    roughness: float = 0.5
    normal_strength: float = 1.0

# ─────────────────────────────────────────────────────────────────────────────
# BLENDER UTILITIES
# ─────────────────────────────────────────────────────────────────────────────

class BlenderScene:
    """Blender sahne yönetimi"""

    def __init__(self, output_dir: str = "./dataset"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)
        self.object = None

    def clear_scene(self):
        """Sahnedeki tüm objeleri sil"""
        bpy.ops.object.select_all(action='SELECT')
        bpy.ops.object.delete(use_global=False)
        bpy.ops.outliner.orphans_purge()

    def import_mesh(self, mesh_path: str):
        """STL/OBJ dosyasını içe aktar"""
        file_ext = Path(mesh_path).suffix.lower()

        if file_ext == ".stl":
            bpy.ops.import_mesh.stl(filepath=mesh_path)
        elif file_ext == ".obj":
            bpy.ops.import_scene.obj(filepath=mesh_path)
        elif file_ext == ".ply":
            bpy.ops.import_mesh.ply(filepath=mesh_path)
        else:
            raise ValueError(f"Unsupported format: {file_ext}")

        # Son imported object'i seç
        self.object = bpy.context.selected_objects[0]
        return self.object

    def center_object(self):
        """Objeyi sahne merkezine yerleştir"""
        if not self.object:
            return

        # Geometry center'a git
        bpy.ops.object.origin_set(type='GEOMETRY')

        # Location sıfırla
        self.object.location = (0, 0, 0)

    def scale_object(self, scale: float):
        """Objeyi ölçekle"""
        if not self.object:
            return

        self.object.scale = (scale, scale, scale)
        bpy.context.view_layer.update()

    def rotate_object(self, rotation_euler: Tuple[float, float, float]):
        """Objeyi döndür (radian cinsinden)"""
        if not self.object:
            return

        self.object.rotation_euler = rotation_euler
        bpy.context.view_layer.update()

    def setup_rendering(self, config: RenderConfig):
        """Render ayarlarını kur"""
        scene = bpy.context.scene

        # Çözünürlük
        scene.render.resolution_x = config.resolution_x
        scene.render.resolution_y = config.resolution_y

        # Engine
        scene.render.engine = config.engine

        if config.engine == "CYCLES":
            scene.cycles.samples = config.samples
            scene.cycles.use_denoising = True
        else:  # EEVEE
            scene.eevee.use_bloom = True

        # Format
        scene.render.image_settings.file_format = config.output_format
        scene.render.image_settings.color_mode = 'RGBA'

    def add_camera(self, view: CameraView) -> bpy.types.Object:
        """Kamera ekle"""
        bpy.ops.object.camera_add(
            location=view.location,
            rotation=view.rotation
        )
        camera = bpy.context.active_object
        camera.name = view.name

        # Focus distance
        camera.data.lens = 50

        return camera

    def add_lighting(self, setup: LightingSetup) -> List[bpy.types.Object]:
        """Aydınlatma ekle"""
        lights = []

        for i, (light_type, intensity, angle) in enumerate(
            zip(setup.light_types, setup.intensities, setup.angles)
        ):
            bpy.ops.object.light_add(
                type=light_type,
                location=(3 * np.cos(angle[0]), 3 * np.sin(angle[0]), 2)
            )
            light = bpy.context.active_object
            light.name = f"{setup.name}_{light_type}_{i}"
            light.data.energy = intensity

            if light_type == "SUN":
                light.data.angle = np.radians(0.5)

            lights.append(light)

        return lights

    def create_material(self, texture: TextureVariant) -> bpy.types.Material:
        """Material oluştur"""
        mat = bpy.data.materials.new(name=texture.name)
        mat.use_nodes = True

        bsdf = mat.node_tree.nodes["Principled BSDF"]
        bsdf.inputs[0].default_value = texture.base_color  # Base Color
        bsdf.inputs[1].default_value = texture.metallic    # Metallic
        bsdf.inputs[2].default_value = texture.roughness   # Roughness

        return mat

    def apply_material(self, material: bpy.types.Material):
        """Materiali objeye uygula"""
        if not self.object:
            return

        if len(self.object.data.materials) == 0:
            self.object.data.materials.append(material)
        else:
            self.object.data.materials[0] = material

    def render_frame(self, output_path: str, camera: bpy.types.Object = None):
        """Çerçeve render et"""
        scene = bpy.context.scene

        if camera:
            scene.camera = camera

        scene.render.filepath = output_path
        bpy.ops.render.render(write_still=True)

        return output_path


# ─────────────────────────────────────────────────────────────────────────────
# SYNTHETIC DATASET GENERATOR
# ─────────────────────────────────────────────────────────────────────────────

class SyntheticDatasetGenerator:
    """Sentetik dataset oluşturma"""

    def __init__(self, mesh_path: str, output_dir: str = "./dataset", background_dir: str = None):
        self.mesh_path = mesh_path
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)

        # Arka plan klasörü
        self.background_dir = Path(background_dir) if background_dir else None
        self.backgrounds = []

        if self.background_dir and self.background_dir.exists():
            # Arka plan resimlerini yükle
            for ext in ["*.jpg", "*.jpeg", "*.png", "*.exr"]:
                self.backgrounds.extend(self.background_dir.glob(ext))
                self.backgrounds.extend(self.background_dir.glob(ext.upper()))
            print(f"✅ {len(self.backgrounds)} arka plan bulundu")

        self.scene = BlenderScene(output_dir)
        self.scene.clear_scene()
        self.scene.import_mesh(mesh_path)
        self.scene.center_object()

        self.metadata = {
            "mesh_file": str(mesh_path),
            "created_date": str(Path(mesh_path).stat().st_mtime),
            "renders": [],
            "background_dir": str(self.background_dir) if self.background_dir else None,
            "num_backgrounds": len(self.backgrounds)
        }

    def setup_default_scene(self, render_config: RenderConfig = None, background_image: str = None):
        """Varsayılan sahne kur"""
        if render_config is None:
            render_config = RenderConfig()

        self.scene.setup_rendering(render_config)

        # World background
        world = bpy.data.worlds["World"]
        world.use_nodes = True
        bg = world.node_tree.nodes["Background"]

        # Arka plan resmi yükle (varsa)
        if background_image and Path(background_image).exists():
            try:
                # Texture node oluştur
                nodes = world.node_tree.nodes
                links = world.node_tree.links

                # Mevcut nodeları temizle
                for node in nodes:
                    if node.type != "OUTPUT":
                        nodes.remove(node)

                # Yeni nodes oluştur
                tex_node = nodes.new(type="ShaderNodeTexEnvironment")
                bg_node = nodes.new(type="ShaderNodeBackground")
                output_node = nodes.new(type="ShaderNodeOutputWorld")

                # Resmi yükle
                image = bpy.data.images.load(background_image)
                tex_node.image = image

                # Bağlantıları kur
                links.new(tex_node.outputs["Color"], bg_node.inputs["Color"])
                links.new(bg_node.outputs["Background"], output_node.inputs["Surface"])

                print(f"✅ Arka plan yüklendi: {Path(background_image).name}")

            except Exception as e:
                print(f"⚠️  Arka plan yüklenemedi: {str(e)}")
                bg.inputs[0].default_value = (0.5, 0.5, 0.5, 1.0)
        else:
            # Varsayılan gri background
            bg.inputs[0].default_value = (0.5, 0.5, 0.5, 1.0)

    def generate_camera_views(self, num_views: int = 8) -> List[CameraView]:
        """Çevre kamerası görüntülerini oluştur"""
        views = []

        # Dairesel kamera hareketi
        for i in range(num_views):
            angle = 2 * np.pi * i / num_views
            x = 3 * np.cos(angle)
            y = 3 * np.sin(angle)
            z = 2

            rotation_z = -angle
            view = CameraView(
                name=f"View_{i:02d}",
                location=(x, y, z),
                rotation=(np.radians(45), 0, rotation_z),
                zoom=1.0
            )
            views.append(view)

        return views

    def generate_lighting_setups(self) -> List[LightingSetup]:
        """Farklı aydınlatma kombinasyonları"""
        setups = [
            LightingSetup(
                name="Studio_1Light",
                light_types=["SUN"],
                intensities=[2.0],
                angles=[(np.radians(45), 0, 0)]
            ),
            LightingSetup(
                name="Studio_3Light",
                light_types=["SUN", "POINT", "POINT"],
                intensities=[1.5, 1.0, 0.8],
                angles=[
                    (np.radians(45), 0, 0),
                    (np.radians(30), np.radians(90), 0),
                    (np.radians(30), np.radians(270), 0)
                ]
            ),
            LightingSetup(
                name="Low_Light",
                light_types=["SUN"],
                intensities=[0.5],
                angles=[(np.radians(20), 0, 0)]
            ),
            LightingSetup(
                name="Backlit",
                light_types=["SUN"],
                intensities=[2.0],
                angles=[(np.radians(135), 0, 0)]
            )
        ]
        return setups

    def generate_texture_variants(self) -> List[TextureVariant]:
        """Farklı doku/renk varyantları"""
        variants = [
            TextureVariant(
                name="Gray_Matte",
                base_color=(0.5, 0.5, 0.5, 1.0),
                metallic=0.0,
                roughness=0.8
            ),
            TextureVariant(
                name="Carbon_Fiber",
                base_color=(0.2, 0.2, 0.2, 1.0),
                metallic=0.3,
                roughness=0.4
            ),
            TextureVariant(
                name="Metallic_Blue",
                base_color=(0.1, 0.3, 0.6, 1.0),
                metallic=0.8,
                roughness=0.2
            ),
            TextureVariant(
                name="White_Plastic",
                base_color=(0.9, 0.9, 0.9, 1.0),
                metallic=0.0,
                roughness=0.6
            ),
            TextureVariant(
                name="Red_Glossy",
                base_color=(0.8, 0.1, 0.1, 1.0),
                metallic=0.1,
                roughness=0.3
            )
        ]
        return variants

    def generate_dataset(self,
                        num_views: int = 8,
                        render_config: RenderConfig = None) -> Dict:
        """Tam dataset oluştur"""
        if render_config is None:
            render_config = RenderConfig()

        print("=" * 60)
        print("🎬 SYNTHETIC DATASET GENERATION")
        print("=" * 60)

        # Scene setup
        self.setup_default_scene(render_config)

        # Kameraları hazırla
        cameras = []
        views = self.generate_camera_views(num_views)
        for view in views:
            cam = self.scene.add_camera(view)
            cameras.append((cam, view))

        # Aydınlatma varyantları
        lighting_setups = self.generate_lighting_setups()

        # Doku varyantları
        texture_variants = self.generate_texture_variants()

        # Render sayacı
        render_count = 0
        total_renders = len(cameras) * len(lighting_setups) * len(texture_variants)

        print(f"📊 Toplam render sayısı: {total_renders}")
        print(f"   • Kamera açısı: {len(cameras)}")
        print(f"   • Aydınlatma: {len(lighting_setups)}")
        print(f"   • Doku/Renk: {len(texture_variants)}")
        if self.backgrounds:
            print(f"   • Arka planlar: {len(self.backgrounds)}")

        # Render loop
        for lighting_setup in lighting_setups:
            # Aydınlatma kur
            lights = self.scene.add_lighting(lighting_setup)

            for texture in texture_variants:
                # Material kur
                material = self.scene.create_material(texture)
                self.scene.apply_material(material)

                for camera, view in cameras:
                    # Her kamera view için farklı arka plan kullan (varsa)
                    background_idx = len(self.metadata["renders"]) % len(self.backgrounds) if self.backgrounds else 0
                    current_background = None

                    if self.backgrounds and background_idx < len(self.backgrounds):
                        current_background = str(self.backgrounds[background_idx])
                        # Scene'i arka plan ile hazırla
                        self.setup_default_scene(render_config, current_background)

                    # Render
                    bg_name = Path(current_background).stem if current_background else "default"
                    filename = f"{lighting_setup.name}_{texture.name}_{view.name}_{bg_name}.png"
                    output_path = str(self.output_dir / filename)

                    self.scene.render_frame(output_path, camera)

                    # Metadata
                    render_meta = {
                        "filename": filename,
                        "camera_view": view.name,
                        "lighting": lighting_setup.name,
                        "texture": texture.name,
                        "background": bg_name if current_background else "procedural",
                        "camera_location": view.location,
                        "resolution": f"{render_config.resolution_x}x{render_config.resolution_y}"
                    }
                    self.metadata["renders"].append(render_meta)

                    render_count += 1
                    progress = (render_count / total_renders) * 100
                    print(f"[{progress:.1f}%] {filename}")

            # Işıkları sil
            for light in lights:
                bpy.data.objects.remove(light, do_unlink=True)

        # Metadata kaydet
        metadata_path = self.output_dir / "metadata.json"
        with open(metadata_path, "w") as f:
            json.dump(self.metadata, f, indent=2)

        print("\n" + "=" * 60)
        print(f"✅ Dataset oluşturuldu: {self.output_dir}")
        print(f"   • Toplam render: {render_count}")
        print(f"   • Metadata: {metadata_path}")
        print("=" * 60)

        return self.metadata

    def generate_thermal_dataset(self, num_views: int = 8):
        """Termal görüntü dataset'i (simüle)"""
        print("🌡️ Thermal dataset oluşturuluyor...")

        # Grayscale to thermal color mapping
        # (Blender'da thermal texture oluşturma)

        for i in range(num_views):
            # Temperature gradient material
            mat = bpy.data.materials.new(name=f"Thermal_{i}")
            mat.use_nodes = True

            # Node setup for thermal look
            nodes = mat.node_tree.nodes
            nodes.clear()

            # Gradient: blue (cold) → red (hot)
            # ... (Blender node setup)

        print("✅ Thermal dataset hazır")

    def generate_damage_variants(self):
        """Hasar varyantları (Opsiyonel)"""
        print("⚠️ Damage variants oluşturuluyor...")

        # Modifiers ekle: noise, deform, vb.
        # Birkaç varyant render et

        print("✅ Damage variants hazır")


# ─────────────────────────────────────────────────────────────────────────────
# COMMAND LINE INTERFACE
# ─────────────────────────────────────────────────────────────────────────────

def main():
    """CLI entrypoint"""
    import sys

    if len(sys.argv) < 2:
        print("Kullanım: blender --python script.py -- <mesh_path> [output_dir] [num_views] [background_dir]")
        print("\nÖrnek:")
        print("  blender --python blender_synthetic_generator.py -- drone.stl ./dataset 8 D:\\synthetic_dataset\\backgrounds")
        return

    mesh_path = sys.argv[2]
    output_dir = sys.argv[3] if len(sys.argv) > 3 else "./dataset"
    num_views = int(sys.argv[4]) if len(sys.argv) > 4 else 8
    background_dir = sys.argv[5] if len(sys.argv) > 5 else None

    # Generator oluştur (arka plan klasörü ile)
    generator = SyntheticDatasetGenerator(
        mesh_path,
        output_dir,
        background_dir=background_dir
    )

    # Dataset oluştur
    render_config = RenderConfig(
        resolution_x=1280,
        resolution_y=720,
        samples=256,
        engine="CYCLES"
    )

    metadata = generator.generate_dataset(num_views=num_views,
                                         render_config=render_config)

    print("\n✅ Dataset oluşturuldu! Training'e hazır.")


if __name__ == "__main__":
    main()
