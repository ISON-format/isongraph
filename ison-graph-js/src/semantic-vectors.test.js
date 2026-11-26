/**
 * Semantic golden corpus runner for the JavaScript port.
 * Reads vectors/semantic/manifest.ison with ison-parser and checks the 'ts'
 * column of its three tables (vectors, relations, api). Grammar, columns and
 * the normal-form listing format: vectors/semantic/README.md.
 *
 * `normalize` below is a test oracle for ISONGraph-Semantic/2-draft sections
 * 1-2, not the Semantic/2 implementation; it computes no digest because the
 * digest encoding (section 3) is not frozen. JavaScript cannot tell the
 * integer 1e20 from the float 1e20, so a number that is an integer beyond
 * 2^53 is reported as JS_UNSAFE_INTEGER (the section 1.2 JavaScript binding
 * rule) and accepted wherever the manifest expects either int64-range reason.
 */
import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { loads as parse, Reference } from 'ison-parser';
import { ISONGraph } from './index.js';

const SEMANTIC = resolve(dirname(fileURLToPath(import.meta.url)), '..', '..', 'vectors', 'semantic');
const PORT = 'js';
const MULTIGRAPH_FORMAT = 'ison-graph-multigraph-v1';
const INT64_MIN = -(2n ** 63n);
const INT64_MAX = 2n ** 63n - 1n;

const read = (rel) => readFileSync(resolve(SEMANTIC, rel), 'utf8');
const tables = {};
for (const b of parse(read('manifest.ison')).blocks) {
  if (b.kind === 'table') tables[b.name] = b.rows;
}
const rows = tables.vectors;
const relations = tables.relations;
const api = tables.api;
const byId = new Map(rows.map(r => [r.id, r]));

// ---------------------------------------------------------------------------
// Test oracle: Semantic/2 sections 1-2 over a parsed ISON document
// ---------------------------------------------------------------------------

class OutOfDomain extends Error {
  constructor(reason) {
    super(reason);
    this.reason = reason;
  }
}

const bytes = (s) => Buffer.from(s, 'utf8');
const cmp = (a, b) => Buffer.compare(a, b);

function quote(s) {
  let out = '"';
  for (const ch of s) {
    const cp = ch.codePointAt(0);
    if (ch === '"') out += '\\"';
    else if (ch === '\\') out += '\\\\';
    else if (cp >= 0x20 && cp <= 0x7e) out += ch;
    else out += '\\u{' + cp.toString(16).toUpperCase() + '}';
  }
  return out + '"';
}

function hasLoneSurrogate(s) {
  for (let i = 0; i < s.length; i++) {
    const c = s.charCodeAt(i);
    if (c >= 0xd800 && c <= 0xdbff) {
      const d = s.charCodeAt(i + 1);
      if (d >= 0xdc00 && d <= 0xdfff) i++;
      else return true;
    } else if (c >= 0xdc00 && c <= 0xdfff) return true;
  }
  return false;
}

function valueForm(v) {
  if (typeof v === 'boolean') return ['BOOL', String(v)];
  if (typeof v === 'bigint') {
    if (v < INT64_MIN || v > INT64_MAX) throw new OutOfDomain('INTEGER_OUT_OF_INT64');
    return ['INT64', v.toString()];
  }
  if (typeof v === 'number') {
    if (!Number.isFinite(v)) throw new OutOfDomain('NONFINITE_FLOAT');
    if (Number.isInteger(v)) {
      if (!Number.isSafeInteger(v)) throw new OutOfDomain('JS_UNSAFE_INTEGER');
      return ['INT64', v === 0 ? '0' : String(v)];
    }
    const view = new DataView(new ArrayBuffer(8));
    view.setFloat64(0, v);
    return ['FLOAT64', view.getBigUint64(0).toString(16).toUpperCase().padStart(16, '0')];
  }
  if (typeof v === 'string') {
    if (hasLoneSurrogate(v)) throw new OutOfDomain('INVALID_UNICODE_SCALAR');
    return ['STRING', v];
  }
  if (Array.isArray(v) || (v !== null && typeof v === 'object' && !(v instanceof Reference))) {
    throw new OutOfDomain('CONTAINER_PROPERTY');
  }
  throw new Error(`oracle has no rule for ${typeof v}`);
}

function idForm(v) {
  if (v === null || v === undefined || typeof v === 'boolean') throw new OutOfDomain('INVALID_NODE_ID_TYPE');
  if (typeof v === 'number' && !Number.isInteger(v)) throw new OutOfDomain('INVALID_NODE_ID_TYPE');
  return valueForm(v);
}

const render = ([kind, payload]) =>
  kind === 'STRING' ? `STRING(${quote(payload)})`
    : kind === 'FLOAT64' ? `FLOAT64(0x${payload})`
    : kind === 'BOOL' ? `BOOL(${payload})`
    : `INT64(${payload})`;

const refText = (r) => `${r[0]}:${render(r[1])}`;
const refId = (r) => JSON.stringify([r[0], r[1][0], r[1][1]]);

/** Section 2.3 NodeRef order: type bytes, then INT64 < STRING, ints numerically, strings by UTF-8 bytes. */
function refCmp(a, b) {
  const t = cmp(bytes(a[0]), bytes(b[0]));
  if (t !== 0) return t;
  const ra = a[1][0] === 'INT64' ? 0 : 1;
  const rb = b[1][0] === 'INT64' ? 0 : 1;
  if (ra !== rb) return ra - rb;
  if (ra === 0) {
    const x = BigInt(a[1][1]);
    const y = BigInt(b[1][1]);
    return x < y ? -1 : x > y ? 1 : 0;
  }
  return cmp(bytes(a[1][1]), bytes(b[1][1]));
}

const propsText = (props) =>
  '{' + [...props.entries()]
    .sort((x, y) => cmp(bytes(x[0]), bytes(y[0])))
    .map(([k, v]) => `${k}=${render(v)}`)
    .join(', ') + '}';

function propsOf(row, skip) {
  const out = new Map();
  for (const [name, v] of Object.entries(row)) {
    if (skip.has(name) || v === null || v === undefined) continue; // null members are elided (1.3)
    out.set(name, valueForm(v));
  }
  return out;
}

function normalize(doc) {
  let directed = true;
  let multigraph = false;
  for (const b of doc.blocks) {
    if (b.kind === 'meta' && b.name === 'graph') {
      for (const row of b.rows) {
        if ('directed' in row) directed = Boolean(row.directed);
        if (row.format === MULTIGRAPH_FORMAT) multigraph = true;
      }
    }
  }
  try {
    const nodes = new Map();
    for (const b of doc.blocks) {
      if (b.kind !== 'nodes') continue;
      for (const row of b.rows) {
        const ref = [b.name, idForm(row.id)];
        nodes.set(refId(ref), { ref, props: propsOf(row, new Set(['id'])) });
      }
    }
    for (const { ref } of nodes.values()) {
      if (ref[1][0] === 'INT64' && nodes.has(refId([ref[0], ['STRING', ref[1][1]]]))) {
        throw new OutOfDomain('AMBIGUOUS_NODE_REFERENCE');
      }
    }
    const resolve = (r) => {
      const text = String(r.id);
      let ref = [r.type, ['STRING', text]];
      if (!nodes.has(refId(ref)) && /^-?[0-9]+$/.test(text)) ref = [r.type, ['INT64', BigInt(text).toString()]];
      if (!nodes.has(refId(ref))) throw new OutOfDomain('INVALID_EDGE_ADDRESS');
      return ref;
    };

    const groups = new Map();
    for (const b of doc.blocks) {
      if (b.kind !== 'edges') continue;
      for (const row of b.rows) {
        let ordinal = '0';
        const skip = new Set(['source', 'target']);
        if (multigraph) {
          const key = row.key;
          if (typeof key !== 'number' || !Number.isInteger(key) || key < 0) throw new OutOfDomain('INVALID_EDGE_ADDRESS');
          ordinal = String(key);
          skip.add('key');
        }
        const src = resolve(row.source);
        const tgt = resolve(row.target);
        const [lo, hi] = directed ? [src, tgt] : refCmp(src, tgt) <= 0 ? [src, tgt] : [tgt, src];
        const rec = { src, tgt, lo, hi, rel: b.name, ordinal, props: propsOf(row, skip) };
        const gk = JSON.stringify([refId(lo), rec.rel, refId(hi), ordinal]);
        if (!groups.has(gk)) groups.set(gk, []);
        groups.get(gk).push(rec);
      }
    }
    const edges = [];
    for (const recs of groups.values()) {
      if (directed) {
        if (recs.length > 1) throw new OutOfDomain('INVALID_EDGE_ADDRESS');
      } else {
        if (recs.length > 2) throw new OutOfDomain('UNDIRECTED_EDGE_CONFLICT');
        if (recs.length === 2) {
          if (refId(recs[0].lo) !== refId(recs[0].hi) && refId(recs[0].src) === refId(recs[1].src)) {
            throw new OutOfDomain('INVALID_EDGE_ADDRESS');
          }
          if (propsText(recs[0].props) !== propsText(recs[1].props)) throw new OutOfDomain('UNDIRECTED_EDGE_CONFLICT');
        }
      }
      edges.push(recs[0]);
    }
    edges.sort((a, b) =>
      refCmp(a.lo, b.lo) || cmp(bytes(a.rel), bytes(b.rel)) || refCmp(a.hi, b.hi) || cmp(bytes(a.ordinal), bytes(b.ordinal)));

    const lines = [`header directed=${directed} multigraph=${multigraph}`];
    for (const n of [...nodes.values()].sort((a, b) => refCmp(a.ref, b.ref))) {
      lines.push(`node ${refText(n.ref)} ${propsText(n.props)}`);
    }
    for (const e of edges) {
      lines.push(`edge ${refText(e.lo)} ${e.rel} ${refText(e.hi)} ordinal=${render(['STRING', e.ordinal])} ${propsText(e.props)}`);
    }
    return { status: 'identifiable', reason: null, listing: lines.join('\n') + '\n' };
  } catch (e) {
    if (e instanceof OutOfDomain) return { status: 'out_of_domain', reason: e.reason, listing: null };
    throw e;
  }
}

const classify = (text) => normalize(parse(text));

/** JS_UNSAFE_INTEGER stands for either int64-range reason: the integer/float distinction is not observable. */
const reasonMatches = (expected, got) =>
  got === expected ||
  (got === 'JS_UNSAFE_INTEGER' && (expected === 'INTEGER_OUT_OF_INT64' || expected === 'INTEGRAL_FLOAT_OUT_OF_INT64'));

// ---------------------------------------------------------------------------
// Runner
// ---------------------------------------------------------------------------

const load = (text) => ISONGraph.fromIson(text);
const emit = (g) => g.toIson() + '\n';

describe('Semantic golden corpus (js)', () => {
  it('is admitted: no todo in its column', () => {
    for (const r of [...rows, ...api]) expect(r[PORT], r.id).not.toBe('todo');
  });

  describe.each(rows.map(r => [r.id, r]))('vector %s', (_id, row) => {
    it('behaves as the manifest says', () => {
      const expectation = row[PORT];
      const text = read(row.file);

      if (expectation !== 'pass:lossy') {
        const n = classify(text);
        expect(n.status).toBe(row.semantic);
        expect(reasonMatches(row.reason, n.reason), `reason ${n.reason} vs ${row.reason}`).toBe(true);
        if (row.semantic === 'identifiable') expect(n.listing).toBe(read(row.normal));
      }

      if (expectation.startsWith('reject:')) {
        let name = '';
        try {
          load(text);
        } catch (e) {
          name = e.name ?? e.constructor.name;
        }
        expect(name).toBe(expectation.slice('reject:'.length));
        return;
      }

      const g = load(text);
      expect(g.directed).toBe(row.directed);
      expect(g.nodeCount()).toBe(row.nodes);
      expect(g.edgeCount()).toBe(row.edges);

      const out = emit(g);
      const again = emit(load(out));
      if (expectation === 'pass') {
        expect(out).toBe(text);
      } else if (expectation === 'pass:canonicalized') {
        expect(out).toBe(read(row.canonical));
        expect(again).toBe(out);
      } else if (expectation === 'pass:lossy') {
        expect(out, 'pass:lossy but output equals the file - promote the cell to pass').not.toBe(text);
        expect(again).toBe(out);
      } else if (expectation === 'defect') {
        expect(again).toBe(out);
      } else if (expectation === 'defect:unstable') {
        expect(again, 'defect:unstable but output is idempotent - the cell is stale').not.toBe(out);
      } else {
        throw new Error(`unknown expectation ${JSON.stringify(expectation)} for ${PORT}`);
      }
    });
  });

  describe.each(relations.map(r => [r.id, r]))('relation %s', (_id, rel) => {
    it('holds', () => {
      const a = read(byId.get(rel.a).file);
      const b = read(byId.get(rel.b).file);
      const fa = classify(a);
      const fb = classify(b);
      expect(JSON.stringify(fa) === JSON.stringify(fb)).toBe(rel.semantic === 'equal');
      const sha = (s) => createHash('sha256').update(s, 'utf8').digest('hex');
      expect(sha(a) === sha(b)).toBe(rel.artifact === 'same');
    });
  });

  const ops = {
    'nan-property': () => NaN,
    'inf-property': () => Infinity,
    'lone-surrogate-property': () => String.fromCharCode(0xd800),
    'list-property': () => ['a', 'b'],
    'dict-property': () => ({ a: 1 }),
    'int-beyond-int64-property': () => 10n ** 20n,
    'float-exponent-property': () => 1e-7,
  };

  describe.each(api.map(r => [r.id, r]))('api %s', (_id, row) => {
    it('behaves as the manifest says', () => {
      const value = ops[row.op]();
      let verdict = ['identifiable', null];
      try {
        valueForm(value);
      } catch (e) {
        if (!(e instanceof OutOfDomain)) throw e;
        verdict = ['out_of_domain', e.reason];
      }
      expect(verdict).toEqual([row.semantic, row.reason]);

      const expectation = row[PORT];
      const g = new ISONGraph('g');
      if (expectation.startsWith('reject:')) {
        let name = '';
        try {
          g.addNode('p', 1, { x: value });
        } catch (e) {
          name = e.name;
        }
        expect(name).toBe(expectation.slice('reject:'.length));
        return;
      }

      g.addNode('p', 1, { x: value });
      if (expectation.startsWith('accept:unwritable:')) {
        let name = '';
        try {
          g.toIson();
        } catch (e) {
          name = e.name;
        }
        expect(name).toBe(expectation.slice('accept:unwritable:'.length));
        return;
      }
      const out = g.toIson();
      if (expectation === 'accept:unencodable') {
        // A lone surrogate has no UTF-8 form: the encoder substitutes U+FFFD.
        expect(Buffer.from(out, 'utf8').toString('utf8')).not.toBe(out);
        return;
      }
      const after = ISONGraph.fromIson(out).getNode('p', 1).properties.x;
      const same = typeof after === typeof value && after === value;
      expect(same, `reloaded ${String(after)} (${typeof after}) from ${String(value)}`).toBe(expectation === 'accept');
    });
  });
});
