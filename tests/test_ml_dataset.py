"""Sentetik dataset → YOLO annotasyon dönüşümü testleri.

Düzeltilen kusuru dondurur: DatasetPreparator artık Blender metadata'sındaki
GERÇEK bbox'ı (bbox_yolo) + class_id'yi kullanır; görünmeyen render'ları atlar;
yalnızca eski (bbox'sız) metadata için kaba tahmine düşer.
"""
import json

import pytest

from ml_training_integration import DatasetPreparator, MLTrainer


def _meta(path, renders):
    path.write_text(json.dumps({"renders": renders}))
    return str(path)


def test_trainer_honest_failure_no_fabricated_metrics(monkeypatch, tmp_path):
    """DÜRÜSTLÜK: ultralytics yok/eğitim hatasında SAHTE metrik (eski 0.92 mAP) DÖNMEZ —
    status=FAILED, results=None. Uygulamanın V&V-dürüstlük ilkesi ML'e de uygulanır."""
    import sys
    import types
    fake = types.ModuleType("ultralytics")
    class _YOLO:                                       # noqa: N801
        def __init__(self, *a, **k):
            raise RuntimeError("test: ultralytics yok")
    fake.YOLO = _YOLO
    monkeypatch.setitem(sys.modules, "ultralytics", fake)
    r = MLTrainer().train_model(str(tmp_path / "data.yaml"))
    assert r["status"] == "FAILED" and r["results"] is None and "error" in r
    ev = MLTrainer().evaluate_model(str(tmp_path / "data.yaml"))
    assert ev["status"] == "FAILED" and ev["map50"] is None
    assert MLTrainer().export_model("onnx") is None    # sahte yol değil


def test_uses_real_bbox_and_class(tmp_path):
    """Gerçek bbox_yolo + class_id aynen kullanılmalı (stub değil)."""
    mf = _meta(tmp_path / "m.json", [
        {"filename": "a.png", "class_id": 1, "visible": True,
         "bbox_yolo": [0.4, 0.55, 0.2, 0.3]},
    ])
    prep = DatasetPreparator(str(tmp_path), str(tmp_path / "out"))
    ann = prep.create_yolo_annotations(mf)
    assert len(ann) == 1
    a = ann[0]
    assert a["class_id"] == 1
    assert (a["center_x"], a["center_y"], a["width"], a["height"]) == (0.4, 0.55, 0.2, 0.3)


def test_skips_invisible_renders(tmp_path):
    """visible=False (nesne çerçeve dışı) eğitime alınmamalı."""
    mf = _meta(tmp_path / "m.json", [
        {"filename": "vis.png", "class_id": 0, "visible": True, "bbox_yolo": [0.5, 0.5, 0.1, 0.1]},
        {"filename": "out.png", "class_id": 0, "visible": False},
    ])
    prep = DatasetPreparator(str(tmp_path), str(tmp_path / "out"))
    ann = prep.create_yolo_annotations(mf)
    assert len(ann) == 1 and ann[0]["image"] == "vis.png"


def test_fallback_for_legacy_metadata(tmp_path):
    """Eski metadata (bbox yok) → merkez-tahmine düşer, crash etmez."""
    mf = _meta(tmp_path / "m.json", [
        {"filename": "old.png", "resolution": "1280x720"},
    ])
    prep = DatasetPreparator(str(tmp_path), str(tmp_path / "out"))
    ann = prep.create_yolo_annotations(mf)
    assert len(ann) == 1
    a = ann[0]
    # %15 marjlı merkez kutu → cx=cy=0.5, w=h=0.7
    assert a["center_x"] == pytest.approx(0.5)
    assert a["width"] == pytest.approx(0.7)


def test_bbox_values_in_valid_range(tmp_path):
    """Normalize bbox değerleri [0,1] aralığında olmalı."""
    mf = _meta(tmp_path / "m.json", [
        {"filename": "a.png", "class_id": 2, "visible": True, "bbox_yolo": [0.5, 0.5, 0.3, 0.4]},
    ])
    prep = DatasetPreparator(str(tmp_path), str(tmp_path / "out"))
    a = prep.create_yolo_annotations(mf)[0]
    for k in ("center_x", "center_y", "width", "height"):
        assert 0.0 <= a[k] <= 1.0
