import { createClient } from "@supabase/supabase-js";

const url = import.meta.env?.VITE_SUPABASE_URL?.trim();
const anonKey = import.meta.env?.VITE_SUPABASE_ANON_KEY?.trim();

export const supabaseConfigured = Boolean(url && anonKey);
export function createSupabaseAuthOptions(storage: Storage) {
  return {
    flowType: "pkce" as const,
    storage,
    persistSession: true,
    autoRefreshToken: true,
    detectSessionInUrl: true,
  };
}

export const supabase = supabaseConfigured
  ? createClient(url!, anonKey!, {
      auth: createSupabaseAuthOptions(window.sessionStorage),
    })
  : null;

export async function getAccessToken(): Promise<string | null> {
  if (!supabase) return null;
  const { data, error } = await supabase.auth.getSession();
  if (error) throw new Error("Could not restore the sign-in session. Sign in again.");
  return data.session?.access_token ?? null;
}
