import { PGlite } from '@electric-sql/pglite';
import { readFile, readdir } from 'node:fs/promises';
import assert from 'node:assert/strict';

const db = await PGlite.create();
try {
 await db.exec('CREATE ROLE anon; CREATE ROLE authenticated; CREATE ROLE service_role BYPASSRLS');
 await db.exec(await readFile(new URL('../001_base.sql', import.meta.url), 'utf8'));
 const root = new URL('../supabase/migrations/', import.meta.url);
 const files = (await readdir(root)).sort();
 const ultima = files.find(f => f.endsWith('_evaluacion_unica_sin_historial.sql'));
 for (const file of files) {
  if (file === ultima || file.includes('_almacenamiento_y_caducidad.sql')) continue;
  await db.exec(await readFile(new URL(file, root), 'utf8'));
 }
 const rpc = async (op, datos) => (await db.query('SELECT public.lf_operar($1,$2) AS r', [op, datos])).rows[0].r;
 const count = async table => (await db.query(`SELECT count(*)::int AS n FROM public.${table}`)).rows[0].n;
 const user = '11111111-1111-4111-8111-111111111111';
 const perfil = {version: 'hotel-2026-11-v39'};
 const resultado = {
  version_motor: 'reglas-hotel-51', huella_entrada: '1'.repeat(64), clasificacion: 'preseleccionada',
  cobertura: 'sin_bases', motivo: 'Se solicita un salón para un evento en Santiago',
  criterios: Object.fromEntries(['vigencia', 'ubicacion', 'pertinencia'].map(c => [c, {
   resultado: 'cumple', motivo: `Criterio ${c} confirmado`, evidencias: [],
  }])),
 };
 const make = (codigo, raw, huella = 'a') => ({
  datos: {id: raw, raw_id: raw, codigo_externo: codigo, modalidad: codigo.includes('-COT') ? 'compra_agil' : 'licitacion',
   nombre: 'Arriendo de salón en Santiago', descripcion: 'Ficha completa '.repeat(2500),
   codigo_estado: codigo.includes('-COT') ? null : 5, estado: 'publicada', fecha_cierre: '2099-01-01T00:00:00Z',
   items: [{posicion_fuente: 1, correlativo: 1, nombre_producto: 'Salón para reunión'}]},
  resultado: {...resultado, version_motor: codigo.includes('-COT') ? 'reglas-hotel-51+ca-2' : 'reglas-hotel-51', huella_entrada: huella.repeat(64)},
  hash_fuente: huella.repeat(64), documentos_version: [],
 });
 const guardar = async lote => (await rpc('guardar', {actor: user, perfil, lote: [lote]})).evaluadas[0].evaluacion_id;
 const a1 = make('100-1-LE26', 1);
 await guardar(a1);
 await guardar(make('100-1-LE26', 2, 'b'));
 const actual = make('100-1-LE26', 3, 'c');
 const eid = await guardar(actual);
 const revisar = async accion => rpc('revision', {codigo: '100-1-LE26', raw_id: 3, hash_fuente: 'c'.repeat(64),
  evaluacion_id: eid, usuario: user, accion, categoria_motivo: 'otro', motivo: 'Decisión actual del hotel'});
 await revisar('confirmar_relevante');
 await revisar('descartar');
 await guardar(make('200-2-LE26', 4));
 await guardar(make('300-3-COT26', 5));
 await guardar(make('300-3-COT26', 6, 'd'));
 await guardar(make('400-4-LE26', 7));
 await db.exec("UPDATE public.oportunidad SET fecha_cierre=now()-interval '1 second' WHERE codigo_externo='400-4-LE26'");
 const antes = (await db.query("SELECT id,evaluacion_id,revision_id,estado_seleccion,hash_fuente FROM public.vw_oportunidades_estado WHERE codigo_externo<>'400-4-LE26' ORDER BY id")).rows;
 assert.ok(await count('evaluacion_filtro') > 4);
 await db.exec(await readFile(new URL(ultima, root), 'utf8'));
 const despues = (await db.query('SELECT id,evaluacion_id,revision_id,estado_seleccion,hash_fuente FROM public.vw_oportunidades_estado ORDER BY id')).rows;
 assert.deepEqual(despues, antes, 'la limpieza conserva las clasificaciones y la última decisión vigente');
 assert.equal(await count('oportunidad'), 3);
 assert.equal(await count('evaluacion_filtro'), 3);
 assert.equal(await count('resultado_criterio'), 9);
 assert.equal(await count('revision_manual'), 1);
 const refs = (await db.query('SELECT entrada_evaluada FROM public.evaluacion_filtro WHERE id=$1', [eid])).rows[0].entrada_evaluada;
 assert.deepEqual(refs, {codigo_externo: '100-1-LE26', raw_id: 3, documentos: []});
 const stamp = (await db.query('SELECT evaluado_en,clave_ejecucion FROM public.evaluacion_filtro WHERE id=$1', [eid])).rows[0];
 assert.equal(await guardar(actual), eid);
 assert.deepEqual((await db.query('SELECT evaluado_en,clave_ejecucion FROM public.evaluacion_filtro WHERE id=$1', [eid])).rows[0], stamp,
  'repetir la misma evaluación no vuelve a escribir ni crea otra ejecución');
 await revisar('confirmar_relevante');
 assert.equal(await count('revision_manual'), 1, 'la nueva decisión reemplaza la anterior');
 assert.equal((await rpc('listar', {codigos: ['100-1-LE26']})).filas[0].estado_seleccion, 'preseleccionada');
 await db.exec('SET ROLE service_role');
 const cambiada = make('100-1-LE26', 8, 'e');
 cambiada.resultado.clasificacion = 'revision_manual';
 assert.equal(await guardar(cambiada), eid, 'cambiar la fuente actualiza la misma evaluación');
 assert.equal(await count('evaluacion_filtro'), 3);
 assert.equal(await count('resultado_criterio'), 9);
 assert.equal(await count('revision_manual'), 0, 'la decisión de una fuente anterior deja de estar vigente');
 await assert.rejects(() => revisar('descartar'), /evaluación cambió/, 'rechaza una revisión con el hash anterior');
 const vieja = {...cambiada, resultado: {...cambiada.resultado, version_motor: 'reglas-hotel-50'}};
 assert.deepEqual((await rpc('guardar', {actor: user, perfil, lote: [vieja]})).evaluadas, [], 'conserva la protección de motores antiguos');
 assert.equal((await rpc('listar', {codigos: ['100-1-LE26']})).filas[0].estado_seleccion, 'revision_manual');
 await db.exec('RESET ROLE');
 await assert.rejects(() => db.query(`INSERT INTO public.evaluacion_filtro(oportunidad_id,perfil_version_id,version_datos,version_motor,cobertura,clasificacion,motivo,entrada_evaluada,metadatos)
  SELECT oportunidad_id,perfil_version_id,version_datos,version_motor,cobertura,clasificacion,motivo,entrada_evaluada,metadatos FROM public.evaluacion_filtro WHERE id=$1`, [eid]), /unique|duplicate/,
  'la restricción impide duplicar una evaluación por escritura directa');
 await db.exec("UPDATE public.oportunidad SET fecha_cierre=now()-interval '1 second' WHERE codigo_externo='300-3-COT26'");
 assert.equal((await db.query('SELECT public.lf_purgar_vencidas() AS n')).rows[0].n, 1);
 assert.equal(await count('oportunidad'), 2);
 assert.equal(await count('evaluacion_filtro'), 2);
 assert.equal(await count('resultado_criterio'), 6, 'la caducidad elimina también los criterios');
 await db.exec('SET ROLE authenticated');
 await assert.rejects(() => rpc('guardar', {actor: user, perfil, lote: [actual]}), /permission denied/);
 await assert.rejects(() => db.query('UPDATE public.evaluacion_filtro SET motivo=motivo'), /permission denied/);
 await db.exec('RESET ROLE');
 console.log('OK: una evaluación por oportunidad, referencias compactas, decisión actual, actualización idempotente, caducidad y permisos.');
} catch (error) {
 console.error(error.message, error.detail || '', error.where || '');
 process.exitCode = 1;
} finally {
 await db.close();
}
