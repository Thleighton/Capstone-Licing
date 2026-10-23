import { crearHandler } from './handler.ts';
function assert(ok: unknown, message='assertion failed') { if (!ok) throw new Error(message); }
const req=(body: unknown, auth='Bearer '+ 'a'.repeat(32))=>new Request('https://test/functions/v1/licing-filtradas',{method:'POST',headers:{Authorization:auth},body:JSON.stringify(body)});
Deno.test('rechaza anónimo antes de acceder a datos', async()=>{
 let calls=0; const h=crearHandler('https://db.test','private', async()=>{calls++;return new Response('{}');});
 assert((await h(req({},''))).status===401); assert(calls===0);
});
Deno.test('token inválido nunca alcanza RPC',async()=>{
 let calls=0;const h=crearHandler('https://db.test','private',async()=>{calls++;return new Response('{}',{status:401});});
 assert((await h(req({operacion:'listar',datos:{}}))).status===401);assert(calls===1);
});
Deno.test('solo permite operaciones declaradas y callback fijo',async()=>{
 let calls=0;const h=crearHandler('https://db.test','private',async(url)=>{calls++;assert(String(url).endsWith('/api/preseleccion/integracion/verificar'));return Response.json({autorizada:true});});
 assert((await h(req({operacion:'sql',datos:{query:'DELETE'}}))).status===422);assert(calls===1);
});
Deno.test('credencial privada no se devuelve al navegador y conflictos son 409',async()=>{
 const h=crearHandler('https://db.test','private',async(url, options)=>{
 if(String(url).includes('verificar'))return Response.json({autorizada:true});
 assert(new Headers(options?.headers).get('Authorization')==='Bearer private');
 return Response.json({code:'40001',message:'detalle interno'},{status:400});
 });
 const response=await h(req({operacion:'revision',datos:{}}));assert(response.status===409);
 assert(!(await response.text()).includes('detalle interno'));
});
Deno.test('no guarda PDF cuya huella difiere',async()=>{
 let calls=0;const h=crearHandler('https://db.test','private',async()=>{calls++;return Response.json({autorizada:true});});
 const response=await h(req({operacion:'guardar_documento',datos:{codigo:'123-1-LE26',contenido_base64:btoa('%PDF-example'),extraccion:{hash_archivo:'incorrecto'}}}));
 assert(response.status===422);assert(calls===1);
});
