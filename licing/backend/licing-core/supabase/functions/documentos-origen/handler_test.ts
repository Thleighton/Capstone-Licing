import { crearHandler } from './handler.ts';
function assert(v: unknown){if(!v)throw Error('Assertion failed');}
const auth='Bearer '+'a'.repeat(32);
const req=(operacion: string,datos: unknown,token=auth)=>new Request('https://origen.test',{method:'POST',headers:{Authorization:token},body:JSON.stringify({operacion,datos})});
Deno.test('sin autenticación no consulta ni modifica Storage',async()=>{
 let llamadas=0;const h=crearHandler('https://original.test','private',async()=>{llamadas++;throw Error();});
 assert((await h(req('subir',{},''))).status===401);assert(llamadas===0);
});
Deno.test('no admite rutas arbitrarias ni huellas falsas',async()=>{
 const h=crearHandler('https://original.test','private',async()=>Response.json({autorizada:true}));
 assert((await h(req('subir',{path:'../otro',contenido_base64:btoa('%PDF-prueba')}))).status===422);
 assert((await h(req('subir',{path:'123-1-LE26/'+'a'.repeat(64)+'.pdf',contenido_base64:btoa('%PDF-prueba')}))).status===422);
});
Deno.test('guarda el PDF solo en el proyecto original',async()=>{
 const pdf='%PDF-1.7 prueba';
 const digest=new Uint8Array(await crypto.subtle.digest('SHA-256',new TextEncoder().encode(pdf)));
 const hash=Array.from(digest,v=>v.toString(16).padStart(2,'0')).join('');
 let subido=false;
 const h=crearHandler('https://original.test','private',async(url,opts)=>{
  if(String(url).includes('/integracion/verificar'))return Response.json({autorizada:true});
  assert(String(url)===`https://original.test/storage/v1/object/licitacion-bases/123-1-LE26/${hash}.pdf`);
  assert(new Headers(opts?.headers).get('Authorization')==='Bearer private');
  subido=true;return Response.json({Key:'archivo'});
 });
 assert((await h(req('subir',{path:`123-1-LE26/${hash}.pdf`,contenido_base64:btoa(pdf)}))).status===200);
 assert(subido);
});
Deno.test('limpieza usa Storage y solo los huérfanos informados por origen',async()=>{
 const path='123-1-LE26/'+'a'.repeat(64)+'.pdf';let borrado=false;
 const h=crearHandler('https://original.test','private',async(url,opts)=>{
  if(String(url).includes('/integracion/verificar'))return Response.json({autorizada:true});
  if(String(url).endsWith('/rpc/documentos_archivos_huerfanos'))return Response.json([path]);
  assert(String(url)==='https://original.test/storage/v1/object/licitacion-bases');
  assert(opts?.method==='DELETE');assert(JSON.parse(String(opts?.body)).prefixes[0]===path);
  borrado=true;return Response.json([]);
 });
 assert((await h(req('limpiar',{}))).status===200);assert(borrado);
});
Deno.test('guarda anexos de Office con su tipo y rechaza firmas o extensiones ajenas',async()=>{
 const docx=new Uint8Array([0x50,0x4b,0x03,0x04,1,2,3]);
 const hash=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',docx)),v=>v.toString(16).padStart(2,'0')).join('');
 let tipo='';
 const h=crearHandler('https://original.test','private',async(url,opts)=>{
  if(String(url).includes('/integracion/verificar'))return Response.json({autorizada:true});
  assert(String(url)===`https://original.test/storage/v1/object/licitacion-bases/123-1-LE26/${hash}.docx`);
  tipo=new Headers(opts?.headers).get('content-type')||'';return Response.json({Key:'archivo'});
 });
 const contenido=btoa(String.fromCharCode(...docx));
 assert((await h(req('subir',{path:`123-1-LE26/${hash}.docx`,contenido_base64:contenido}))).status===200);
 assert(tipo==='application/vnd.openxmlformats-officedocument.wordprocessingml.document');
 assert((await h(req('subir',{path:`123-1-LE26/${hash}.doc`,contenido_base64:contenido}))).status===422);
 assert((await h(req('subir',{path:`123-1-LE26/${hash}.zip`,contenido_base64:contenido}))).status===422);
});
