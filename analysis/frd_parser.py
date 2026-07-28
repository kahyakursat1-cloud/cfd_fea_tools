"""
CalculiX .frd dosya parser.

Sadece nodal blokları (DISP, STRESS) okur. .frd ASCII fixed-width formatında:

Header satırları:
   1C ...
   1U ...
Düğümler:
    2C  N        12
   -1   1 0.00000e+00 0.00000e+00 0.00000e+00
   ...
   -3
Element bloğu (atlanır):
    3C ...
   -1 ...
   -3
Sonuç bloğu:
   100C    name=DISP
   -4  DISP        4    1
   -5  D1          1    2    1    0
   -5  D2          1    2    2    0
   -5  D3          1    2    3    0
   -5  ALL         1    2    0    0    1ALL
   -1   1  v1  v2  v3
   ...
   -3

Stress için 6 bileşen: SXX SYY SZZ SXY SYZ SZX
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np


@dataclass
class FRDResult:
    """Tek bir adıma ait nodal sonuçlar."""
    points: np.ndarray   # (N, 3)
    node_ids: np.ndarray # (N,) — orijinal CalculiX 1-indexed
    fields: dict[str, np.ndarray] = field(default_factory=dict)
    # alanlar: 'DISP': (N, 3), 'STRESS': (N, 6), 'VON_MISES': (N,)
    # Ayrıştırmada ATLANAN satır sayısı — sıfır değilse tepe gerilme EKSİK olabilir.
    atlanan_satir: dict = field(default_factory=lambda: {"dugum": 0, "sonuc": 0})

    def displacement_magnitude(self) -> np.ndarray | None:
        if "DISP" not in self.fields:
            return None
        return np.linalg.norm(self.fields["DISP"], axis=1)

    def von_mises(self) -> np.ndarray | None:
        if "VON_MISES" in self.fields:
            return self.fields["VON_MISES"]
        if "STRESS" not in self.fields:
            return None
        s = self.fields["STRESS"]
        sxx, syy, szz, sxy, syz, szx = (s[:, i] for i in range(6))
        vm = np.sqrt(0.5 * (
            (sxx - syy) ** 2 + (syy - szz) ** 2 + (szz - sxx) ** 2
            + 6.0 * (sxy ** 2 + syz ** 2 + szx ** 2)
        ))
        self.fields["VON_MISES"] = vm
        return vm

    def summary(self) -> str:
        out = [f"FRD: {len(self.node_ids)} düğüm"]
        if "DISP" in self.fields:
            mag = self.displacement_magnitude()
            out.append(f"  Maks deplasman: {mag.max() * 1000:.4f} mm")
        if "STRESS" in self.fields:
            vm = self.von_mises()
            out.append(f"  Maks von Mises: {vm.max() / 1e6:.2f} MPa")
        return "\n".join(out)


def parse_frd(frd_path: Path) -> FRDResult:
    """CalculiX .frd dosyasını parse et.

    Şu an sadece ilk adımı (statik analiz) destekler.
    """
    frd_path = Path(frd_path)
    if not frd_path.exists():
        raise FileNotFoundError(f"FRD dosyası yok: {frd_path}")

    points_list: list[list[float]] = []
    node_ids_list: list[int] = []
    fields: dict[str, np.ndarray] = {}
    # ATLANAN SATIR SAYACI: bozuk satırlar sessizce atlanıyordu. Tepe gerilme o
    # satırlardan birindeyse maksimum SESSİZCE DÜŞÜK çıkar ve SF hükmü iyimser olur.
    # Atlama kaçınılmaz (kısmi/bozuk .frd olur) ama SAYISI görünmeli.
    atlanan = {"dugum": 0, "sonuc": 0}

    # State machine
    in_node_block = False
    in_result_block = False
    current_field_name = ""
    current_field_components = 0
    current_field_data: list[list[float]] = []
    current_field_node_ids: list[int] = []

    with frd_path.open("r") as f:
        for line in f:
            stripped = line.rstrip()

            # Başlangıç tespit kodları:
            #   2C ...  -> node bloğu başı
            #   3C ...  -> element bloğu başı (atlanır)
            #  -4  NAME ... -> sonuç bloğu başı
            #  -1  ...  -> data satırı
            #  -3      -> blok sonu
            if stripped.startswith(" 2C") or stripped.startswith("    2C"):
                in_node_block = True
                in_result_block = False
                continue
            if stripped.startswith(" 3C") or stripped.startswith("    3C"):
                in_node_block = False
                in_result_block = False
                continue
            if stripped.startswith(" -4"):
                # Yeni sonuç bloğu
                # Format: " -4  DISP        4    1"
                tokens = stripped.split()
                # tokens: ['-4', 'DISP', '4', '1']
                if len(tokens) >= 3:
                    current_field_name = tokens[1]
                    current_field_components = int(tokens[2]) - 1  # 1 fazlası: ALL
                    if current_field_components < 1:
                        current_field_components = int(tokens[2])
                # Düzeltme: DISP -> 4 ama gerçek bileşen sayısı 3 (ALL hariç)
                # Bunu -5 satırlarından sayalım (aşağıda override)
                current_field_data = []
                current_field_node_ids = []
                in_result_block = True
                in_node_block = False
                continue
            if stripped.startswith(" -5"):
                # bileşen tanımı; ilki gerçek
                continue
            if stripped.startswith(" -3"):
                if in_result_block and current_field_name and current_field_data:
                    arr = np.array(current_field_data, dtype=np.float64)
                    fields[current_field_name] = arr
                in_node_block = False
                in_result_block = False
                current_field_name = ""
                continue

            if in_node_block and stripped.startswith(" -1"):
                # " -1   1 0.00000e+00 ..."
                # node_id 4..13, sonra 12 char x 3 koordinat
                try:
                    node_id = int(stripped[3:13])
                    x = float(stripped[13:25])
                    y = float(stripped[25:37])
                    z = float(stripped[37:49])
                except (ValueError, IndexError):
                    atlanan["dugum"] += 1
                    continue
                node_ids_list.append(node_id)
                points_list.append([x, y, z])
                continue

            if in_result_block and stripped.startswith(" -1"):
                # " -1   1 v1 v2 v3 ..."
                try:
                    node_id = int(stripped[3:13])
                except ValueError:
                    atlanan["sonuc"] += 1
                    continue
                # Geri kalan değerler 12-karakter genişliğinde
                rest = stripped[13:]
                vals = []
                for i in range(0, len(rest), 12):
                    chunk = rest[i:i + 12].strip()
                    if not chunk:
                        break
                    try:
                        vals.append(float(chunk))
                    except ValueError:
                        break
                if vals:
                    current_field_node_ids.append(node_id)
                    current_field_data.append(vals)
                continue

    if not points_list:
        raise RuntimeError(f"FRD'de düğüm bulunamadı: {frd_path}")

    points = np.array(points_list, dtype=np.float64)
    node_ids = np.array(node_ids_list, dtype=np.int64)

    # Alan boyutlarını standartlaştır: DISP -> 3 bileşen (ALL'ı at), STRESS -> 6
    cleaned: dict[str, np.ndarray] = {}
    for name, arr in fields.items():
        if name == "DISP" and arr.shape[1] >= 3:
            cleaned["DISP"] = arr[:, :3]
        elif name == "STRESS" and arr.shape[1] >= 6:
            cleaned["STRESS"] = arr[:, :6]
        elif name == "FORC" and arr.shape[1] >= 3:
            cleaned["FORC"] = arr[:, :3]
        else:
            cleaned[name] = arr

    if atlanan["dugum"] or atlanan["sonuc"]:
        print(f"[UYARI] .frd ayrıştırmada atlanan satır: {atlanan['dugum']} düğüm, "
              f"{atlanan['sonuc']} sonuç — tepe gerilme EKSİK olabilir "
              f"({frd_path.name})")
    return FRDResult(points=points, node_ids=node_ids, fields=cleaned,
                     atlanan_satir=dict(atlanan))


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Kullanım: python frd_parser.py <frd_dosyası>")
        sys.exit(1)
    r = parse_frd(Path(sys.argv[1]))
    print(r.summary())
