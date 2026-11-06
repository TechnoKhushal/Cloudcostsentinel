import assert from "node:assert/strict";
import test from "node:test";
import { createSupabaseAuthOptions } from "../src/supabase.ts";

test("Supabase Auth uses PKCE and restores/refreshes sessions in the selected storage", () => {
  const storage = {} as Storage;
  const options = createSupabaseAuthOptions(storage);

  assert.equal(options.flowType, "pkce");
  assert.equal(options.storage, storage);
  assert.equal(options.persistSession, true);
  assert.equal(options.autoRefreshToken, true);
  assert.equal(options.detectSessionInUrl, true);
});
