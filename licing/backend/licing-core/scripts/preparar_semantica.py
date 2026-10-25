"""Descarga artefactos de datos fijados; no ejecuta código del repositorio del modelo."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import urllib.request

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.services.semantica_hotel import ARTEFACTOS, MODELO, REVISION

ARCHIVOS = ("config.json", "tokenizer.json", "model.onnx")


def preparar(directorio):
    directorio.mkdir(parents=True, exist_ok=True)
    hashes = {}
    for nombre in ARCHIVOS:
        destino = directorio / nombre
        destino.parent.mkdir(parents=True, exist_ok=True)
        temporal = destino.with_suffix(destino.suffix + ".descarga")
        ruta = "onnx/" + nombre if nombre.endswith(".onnx") else nombre
        with urllib.request.urlopen(f"https://huggingface.co/{MODELO}/resolve/{REVISION}/{ruta}", timeout=60) as respuesta:
            total, firma = 0, hashlib.sha256()
            with temporal.open("wb") as archivo:
                while bloque := respuesta.read(1024 * 1024):
                    total += len(bloque)
                    if total > 1200 * 1024 * 1024:
                        raise ValueError("El artefacto supera el tamaño previsto")
                    firma.update(bloque)
                    archivo.write(bloque)
        hashes[nombre] = firma.hexdigest()
        if hashes[nombre] != ARTEFACTOS[nombre]:
            raise ValueError("La firma del artefacto no coincide con la revisión fijada")
        temporal.replace(destino)
        print(f"Descargado: {nombre} ({total // 1024} KiB)", flush=True)
    (directorio / "manifest.json").write_text(json.dumps({
        "modelo": MODELO, "revision": REVISION, "archivos": hashes,
    }, indent=2), encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directorio", type=Path, default=Path(__file__).resolve().parents[1] / ".modelos" / "semantica-hotel")
    preparar(parser.parse_args().directorio.resolve())
