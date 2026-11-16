"""Excel de licitaciones: solo referencia, comprador y enlace público."""
import asyncio
from io import BytesIO

from openpyxl import Workbook
from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE
from openpyxl.styles import Font, PatternFill, Alignment

from .enlaces import ficha_compra_agil, ficha_oficial


HOJAS = {
    "preseleccionada": "Posibles oportunidades",
    "revision_manual": "Pendientes de revisión",
    "descartada": "Descartadas",
}


async def cargar_clasificaciones(fuentes, consultar, limite=100, concurrencia=3):
    """Lee las clasificaciones en una respuesta ligera y pagina solo por compatibilidad."""
    codigos = list(fuentes)
    if not codigos:
        return {}

    async def cargar_pagina(offset):
        return await consultar("listar", {
            "codigos": codigos, "fuentes": fuentes, "solo_firmas": True,
            "limite": limite, "offset": offset,
        })

    primera = await cargar_pagina(0)
    try:
        total = max(0, int(primera.get("total", len(codigos))))
    except (TypeError, ValueError):
        total = len(codigos)

    filas = list(primera.get("filas", []))
    # La lectura solo_firmas omite paginación. Si el servicio remoto todavía es
    # antiguo y devuelve una página normal, completar las páginas restantes.
    offsets = range(limite, total, limite) if total > len(filas) else ()
    semaforo = asyncio.Semaphore(concurrencia)

    async def cargar_acotada(offset):
        async with semaforo:
            return await cargar_pagina(offset)

    paginas = await asyncio.gather(*(cargar_acotada(offset) for offset in offsets))
    for pagina in paginas:
        filas.extend(pagina.get("filas", []))
    return {str(fila["id"]): fila for fila in filas}


def crear_excel(filas, modalidad="licitacion"):
    compra_agil = modalidad == "compra_agil"
    encabezado_id = "ID Compra Ágil" if compra_agil else "ID licitación"
    ficha = ficha_compra_agil if compra_agil else ficha_oficial
    libro = Workbook()
    libro.remove(libro.active)
    agrupadas = {estado: [] for estado in HOJAS}
    for fila in sorted(filas, key=lambda f: f["codigo_externo"]):
        estado = fila.get("estado_seleccion")
        if estado in agrupadas:
            agrupadas[estado].append(fila)
    for estado, nombre in HOJAS.items():
        hoja = libro.create_sheet(nombre)
        hoja.append([encabezado_id, "Organismo solicitante", "Link directo"])
        for celda in hoja[1]:
            celda.font = Font(bold=True, color="FFFFFF")
            celda.fill = PatternFill("solid", fgColor="087D89")
        for fila in agrupadas[estado]:
            codigo = fila["codigo_externo"]
            valores = [codigo, fila.get("nombre_organismo") or fila.get("nombre_unidad") or "No informado",
                       ficha(codigo) or ""]
            hoja.append([ILLEGAL_CHARACTERS_RE.sub("", str(v)) for v in valores])
            # Los nombres de la fuente son texto, nunca fórmulas de Excel.
            for celda in hoja[hoja.max_row]:
                celda.data_type = "s"
                celda.alignment = Alignment(vertical="top", wrap_text=True)
            enlace = hoja.cell(hoja.max_row, 3)
            if enlace.value:
                enlace.hyperlink = enlace.value
                enlace.style = "Hyperlink"
        hoja.freeze_panes = "A2"
        hoja.auto_filter.ref = hoja.dimensions
        for columna, ancho in (("A", 24), ("B", 65), ("C", 95)):
            hoja.column_dimensions[columna].width = ancho
    salida = BytesIO()
    libro.save(salida)
    return salida.getvalue()
