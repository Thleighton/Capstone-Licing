"""Prueba de aceptación con inferencia real; no consulta ni modifica bases de datos."""
import argparse
from datetime import datetime
import json
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.config import settings
from app.services.preseleccion import CHILE, evaluar_preseleccion
from app.services.compra_agil_preseleccion import evaluar as evaluar_ca
from app.services.semantica_hotel import MODELO, REVISION, VERSION


def cumple(esperado, valor):
    return (valor != "preseleccionada" if esperado == "no_preseleccionada" else
            valor != "descartada" if esperado == "no_descartada" else esperado == valor)


def probar(directorio, salida, archivo_casos, modalidades):
    settings.semantica_modo = "activa"
    settings.semantica_modelo_dir = str(directorio.resolve())
    settings.semantica_url = ""
    casos = json.loads(archivo_casos.read_text(encoding="utf-8"))
    resultados = []
    pruebas = [{**original, "modalidad": modalidad} for original in casos
               for modalidad in (("licitacion", "compra_agil") if modalidades == "ambas" else (original.get("modalidad", "licitacion"),))]
    for n, caso in enumerate(pruebas):
        modalidad = caso["modalidad"]
        caso["esperado"] = caso.get("esperado_" + modalidad, caso["esperado"])
        datos = {"codigo_externo": f"9999-{n + 1}-LE26", "raw_id": n + 1, "codigo_estado": 5,
                 "estado": "Publicada", "fecha_cierre": "2099-12-01T15:00:00-03:00", "items": [], **caso}
        inicio = time.perf_counter()
        if caso.get("modalidad") == "compra_agil":
            datos.update(codigo_externo=f"9999-{n + 1}-COT26", codigo_region=13,
                         region_comprador="Región Metropolitana de Santiago", codigo_estado=None)
            r = evaluar_ca(datos)
        else:
            r = evaluar_preseleccion(datos, ahora=datetime(2026, 10, 25, 12, tzinfo=CHILE))
        esperado = cumple(caso["esperado"], r["clasificacion"])
        if caso["tipo"] in {"negativo", "ambiguo"}:
            esperado = esperado and r["criterios"]["pertinencia"]["resultado"] != "cumple"
        resultado = {"id": caso["id"], "modalidad": modalidad, "tipo": caso["tipo"], "esperado": caso["esperado"],
                     "clasificacion": r["clasificacion"], "correcto": cumple(caso["esperado"], r["clasificacion"]),
                     "rubro": r["criterios"]["pertinencia"]["resultado"],
                     "estado_semantica": r["semantica"]["estado"], "motivo": r["motivo"],
                     "segundos": round(time.perf_counter() - inicio, 3)}
        resultado["correcto"] = esperado
        resultados.append(resultado)
        print(json.dumps(resultado, ensure_ascii=True), flush=True)
    resumen = {"modelo": MODELO, "revision": REVISION, "version": VERSION,
               "casos": len(resultados), "correctos": sum(r["correcto"] for r in resultados),
               "falsos_positivos": sum(r["tipo"] in {"negativo", "ambiguo"} and (r["clasificacion"] == "preseleccionada" or r["rubro"] == "cumple") for r in resultados),
               "evaluadas_semanticamente": sum(r["estado_semantica"] == "evaluada" for r in resultados),
               "omitidas_por_reglas": sum(r["estado_semantica"] == "omitida" for r in resultados),
               "no_disponibles": sum(r["estado_semantica"] == "no_disponible" for r in resultados),
               "resultados": resultados}
    salida.parent.mkdir(parents=True, exist_ok=True)
    salida.write_text(json.dumps(resumen, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in resumen.items() if k != "resultados"}))
    return 0 if resumen["correctos"] == resumen["casos"] and not resumen["no_disponibles"] else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--modelo-dir", type=Path, required=True)
    parser.add_argument("--salida", type=Path, required=True)
    parser.add_argument("--casos", type=Path, default=Path(__file__).resolve().parents[1] / "tests/fixtures/semantica_hotel.json")
    parser.add_argument("--modalidades", choices=["ambas", "original"], default="ambas")
    args = parser.parse_args()
    raise SystemExit(probar(args.modelo_dir, args.salida, args.casos, args.modalidades))
