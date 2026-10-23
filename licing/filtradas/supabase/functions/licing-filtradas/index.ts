import { crearHandler } from "./handler.ts";
Deno.serve(crearHandler(Deno.env.get("SUPABASE_URL")!, Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!));
