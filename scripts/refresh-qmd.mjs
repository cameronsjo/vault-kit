// QMD SDK: refresh only this vault's index; fail on partial embedding errors.
// Usage (through scripts/qmd --vault-refresh): node refresh-qmd.mjs <qmd-package> <collection> [--lexical-only]
import { pathToFileURL, fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";
import { existsSync, realpathSync } from "node:fs";
const pkg = process.argv[2];
const collection = process.argv[3];
const { createStore } = await import(pathToFileURL(resolve(pkg, "dist/index.js")));
const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
// The vault owns its index: <root>/.qmd/. Never the global ~/.cache/qmd one.
const dbPath = resolve(root, ".qmd/index.sqlite");
const configPath = resolve(root, ".qmd/index.yml");
if (!existsSync(dbPath) || !existsSync(configPath)) {
  throw new Error(`No retrieval index at ${dbPath}; run make retrieval-setup.`);
}
const store = await createStore({ dbPath, configPath });
try {
  const found = (await store.listCollections()).find(c => c.name === collection);
  if (!found || realpathSync(found.pwd) !== realpathSync(root)) {
    throw new Error(`Collection ${collection} is not registered against this checkout; run make retrieval-setup (QMD 2.8.x).`);
  }
  console.log(JSON.stringify(await store.update({ collections: [collection] })));
  if (!process.argv.includes("--lexical-only")) {
    // QMD embedding has no collection filter. The index holds only this vault,
    // so this drains this vault's pending hashes and nothing else.
    const result = await store.embed({ maxDocsPerBatch: 8, maxBatchBytes: 1024 * 1024 });
    console.log(JSON.stringify(result));
    if (result.errors > 0) throw new Error(`${result.errors} embedding chunks failed`);
  }
} finally {
  await store.close();
}
