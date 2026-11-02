/**
 * DuckDB-Wasm client for in-browser analytical queries.
 *
 * This module provides a lazy-initialized DuckDB instance that can query
 * Parquet artifacts directly in the browser. When the pipeline exports
 * .parquet files to public/data/, this layer enables SQL queries without
 * any server round-trip.
 *
 * Current status: infrastructure ready. The pipeline currently exports CSV;
 * once `python -m pm25.cli export --format parquet` is added, swap
 * the CSV fetch calls for DuckDB parquet_scan() queries.
 *
 * Usage:
 *   const db = await getDuckDB();
 *   await registerCSV("predictions", "/data/predictions.csv");
 *   const rows = await query("SELECT station, AVG(pred) FROM predictions GROUP BY station");
 */

// DuckDB-Wasm uses ?url imports for WASM/worker bundles. These are
// resolved by the bundler (webpack/turbopack) at build time.
// Type declarations for ?url imports are provided in next-env.d.ts or
// a custom declaration file.
declare module "*.wasm?url" {
  const src: string;
  export default src;
}
declare module "*.worker.js?url" {
  const src: string;
  export default src;
}

let dbInstance: any = null;
let initPromise: Promise<any> | null = null;

/**
 * Get (or lazily create) the singleton DuckDB-Wasm instance.
 * Initialization is ~200ms on first call; subsequent calls are instant.
 *
 * This is a dynamic import to avoid loading the ~3MB WASM bundle until
 * actually needed. The first call triggers the download.
 */
export async function getDuckDB(): Promise<any> {
  if (dbInstance) return dbInstance;
  if (initPromise) return initPromise;

  initPromise = (async () => {
    const duckdb = await import("@duckdb/duckdb-wasm");

    // Use CDN-hosted bundles to avoid bundler issues with ?url imports.
    // This is the recommended approach for Next.js per DuckDB docs.
    const CDN_BUNDLES: any = {
      mvp: {
        mainModule: "https://cdn.jsdelivr.net/npm/@duckdb/duckdb-wasm@1.29.0/dist/duckdb-mvp.wasm",
        mainWorker: "https://cdn.jsdelivr.net/npm/@duckdb/duckdb-wasm@1.29.0/dist/duckdb-browser-mvp.worker.js",
      },
      eh: {
        mainModule: "https://cdn.jsdelivr.net/npm/@duckdb/duckdb-wasm@1.29.0/dist/duckdb-eh.wasm",
        mainWorker: "https://cdn.jsdelivr.net/npm/@duckdb/duckdb-wasm@1.29.0/dist/duckdb-browser-eh.worker.js",
      },
    };

    const bundle = await duckdb.selectBundle(CDN_BUNDLES);
    const worker = new Worker(bundle.mainWorker!);
    const logger = new duckdb.ConsoleLogger();
    const db = new duckdb.AsyncDuckDB(logger, worker);
    await db.instantiate(bundle.mainModule, bundle.pthreadWorker);
    dbInstance = db;
    return db;
  })();

  return initPromise;
}

/**
 * Run a SQL query and return results as an array of objects.
 * Requires DuckDB to be initialized and relevant tables registered.
 */
export async function query<T = Record<string, any>>(sql: string): Promise<T[]> {
  const db = await getDuckDB();
  const conn = await db.connect();
  try {
    const result = await conn.query(sql);
    return result.toArray().map((row: any) => ({ ...row })) as T[];
  } finally {
    await conn.close();
  }
}

/**
 * Register a Parquet file from public/data/ as a queryable table.
 * Example: await registerParquet("predictions", "/data/predictions.parquet");
 * Then: await query("SELECT * FROM predictions WHERE station = 'jadavpur' LIMIT 10");
 */
export async function registerParquet(tableName: string, url: string): Promise<void> {
  const db = await getDuckDB();
  const conn = await db.connect();
  try {
    await conn.query(`CREATE OR REPLACE VIEW ${tableName} AS SELECT * FROM read_parquet('${url}')`);
  } finally {
    await conn.close();
  }
}

/**
 * Register a CSV file from public/data/ as a queryable table.
 * Works with the current pipeline output format.
 */
export async function registerCSV(tableName: string, url: string): Promise<void> {
  const db = await getDuckDB();
  const conn = await db.connect();
  try {
    await conn.query(`CREATE OR REPLACE VIEW ${tableName} AS SELECT * FROM read_csv_auto('${url}')`);
  } finally {
    await conn.close();
  }
}
