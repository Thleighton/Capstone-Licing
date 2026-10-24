// Solo binarios en el proyecto original. Las filas y el texto los administra Core.
const AUTH_URL = 'https://capstone-licing.vercel.app/api/preseleccion/integracion/verificar';
const BUCKET = 'licitacion-bases';
const patron = /^\d+-\d+-[A-Z]+\d+\/[a-f0-9]{64}\.(pdf|docx|xlsx|doc|xls)$/;
// Extensión → tipo MIME y firmas admitidas (PDF, ZIP de Office, contenedor OLE de Office antiguo o cifrado).
const PDF=[0x25,0x50,0x44,0x46,0x2d],ZIP=[0x50,0x4b,0x03,0x04],OLE=[0xd0,0xcf,0x11,0xe0,0xa1,0xb1,0x1a,0xe1];
const FORMATOS: Record<string,{mime:string,firmas:number[][]}> = {
 pdf:{mime:'application/pdf',firmas:[PDF]},
 docx:{mime:'application/vnd.openxmlformats-officedocument.wordprocessingml.document',firmas:[ZIP,OLE]},
 xlsx:{mime:'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',firmas:[ZIP,OLE]},
 doc:{mime:'application/msword',firmas:[OLE]},
 xls:{mime:'application/vnd.ms-excel',firmas:[OLE]},
};
const firmaValida=(bin: Uint8Array,firmas: number[][])=>firmas.some(f=>f.every((b,i)=>bin[i]===b));
const respuesta = (data: unknown, status=200) => Response.json(data,{status,headers:{'cache-control':'no-store'}});
export function crearHandler(base: string, key: string, fetcher: typeof fetch=fetch) {
 const headers={'apikey':key,'Authorization':`Bearer ${key}`,'content-type':'application/json'};
 async function api(path: string, body: unknown, method='POST') {
  const r=await fetcher(base+path,{method,headers,body:JSON.stringify(body),redirect:'error',signal:AbortSignal.timeout(10000)});
  if(!r.ok)throw Error('Storage no disponible');
  return await r.json();
 }
 return async(req: Request)=>{
  if(req.method!=='POST')return respuesta({error:'Método inválido'},405);
  const auth=req.headers.get('authorization')||'';
  if(!/^Bearer [^\s]{16,512}$/.test(auth))return respuesta({error:'Sin autorización'},401);
  try {
   const authRes=await fetcher(AUTH_URL,{headers:{Authorization:auth},redirect:'error',signal:AbortSignal.timeout(8000)});
   if(!authRes.ok || (await authRes.json()).autorizada!==true)return respuesta({error:'Integración no autorizada'},401);
   const reader=req.body?.getReader();if(!reader)return respuesta({error:'Falta cuerpo'},422);
   const chunks: Uint8Array[]=[];let n=0;
   while(true){const {done,value}=await reader.read();if(done)break;n+=value.length;if(n>4200000){await reader.cancel();return respuesta({error:'Archivo demasiado grande'},413);}chunks.push(value);}
   const raw=new Uint8Array(n);let offset=0;for(const c of chunks){raw.set(c,offset);offset+=c.length;}
   const {operacion,datos}=JSON.parse(new TextDecoder().decode(raw));
   if(operacion==='subir'){
    if(!patron.test(datos.path)||typeof datos.contenido_base64!=='string')return respuesta({error:'Documento inválido'},422);
    const formato=FORMATOS[datos.path.split('.').pop()];
    const bin=Uint8Array.from(atob(datos.contenido_base64),(c: string)=>c.charCodeAt(0));
    if(bin.length>3145728||!firmaValida(bin,formato.firmas))return respuesta({error:'Documento inválido'},422);
    const hash=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',bin)),v=>v.toString(16).padStart(2,'0')).join('');
    if(!datos.path.includes('/'+hash+'.'))return respuesta({error:'Huella incorrecta'},422);
    const r=await fetcher(`${base}/storage/v1/object/${BUCKET}/${datos.path}`,{method:'POST',headers:{...headers,'content-type':formato.mime,'x-upsert':'false'},body:bin,redirect:'error',signal:AbortSignal.timeout(10000)});
    if(!r.ok){const e=await r.json().catch(()=>({}));if(r.status!==409&&e.error!=='Duplicate'&&e.statusCode!=='409')throw Error();}
    return respuesta({guardado:true,path:datos.path});
   }
   if(operacion==='firmar'){
    if(!Array.isArray(datos.paths)||datos.paths.length>10||datos.paths.some((p: string)=>!patron.test(p)))return respuesta({error:'Rutas inválidas'},422);
    const result: Record<string,string>={};
    await Promise.all(datos.paths.map(async(p: string)=>{const signed=await api(`/storage/v1/object/sign/${BUCKET}/${p}`,{expiresIn:300});result[p]=base+'/storage/v1'+signed.signedURL;}));
    return respuesta(result);
   }
   if(operacion==='limpiar'){
    const paths=await api('/rest/v1/rpc/documentos_archivos_huerfanos',{});
    if(paths.length)await api(`/storage/v1/object/${BUCKET}`,{prefixes:paths},'DELETE');
    return respuesta({eliminados:paths.length});
   }
   return respuesta({error:'Operación inválida'},422);
  } catch {return respuesta({error:'Almacenamiento temporalmente no disponible'},503);}
 };
}
