// Save (or remove) an OmniRoute provider key straight into its local database.
// The key is read from the environment variable OMNI_KEY_VALUE, never from argv,
// so it does not show up in the process list or shell history.
// Usage: OMNI_KEY_VALUE=... node addkey.mjs add <provider> [name]
//        node addkey.mjs remove <provider>
//        node addkey.mjs list
import { execSync } from "node:child_process";
import { join } from "node:path";

const root = execSync("npm root -g").toString().trim();
const cli = join(root, "omniroute", "bin", "cli");
const { openOmniRouteDb } = await import(join(cli, "sqlite.mjs"));
const store = await import(join(cli, "provider-store.mjs"));

const [cmd, provider, name] = process.argv.slice(2);
const { db } = await openOmniRouteDb();
try {
  store.ensureProviderSchema(db);
  if (cmd === "add") {
    const apiKey = process.env.OMNI_KEY_VALUE;
    if (!provider || !apiKey) throw new Error("need a provider and OMNI_KEY_VALUE");
    const c = store.upsertApiKeyProviderConnection(db, {
      provider, apiKey, name: name || `${provider} (env)`, defaultModel: null, providerSpecificData: null,
    });
    console.log(`saved ${c.provider} key as "${c.name}"`);
  } else if (cmd === "remove") {
    store.removeProviderConnectionByProvider(db, provider);
    console.log(`removed ${provider}`);
  } else if (cmd === "list") {
    for (const c of store.listProviderConnections(db)) console.log(`${c.provider}\t${c.name}\t${c.isActive === 0 ? "off" : "on"}`);
  } else {
    throw new Error("usage: add <provider> [name] | remove <provider> | list");
  }
} finally {
  db.close();
}
