/**
 * Core Conformance Corpus runner for the JavaScript port.
 * Reads vectors/manifest.ison with ison-parser and checks the 'js' column.
 * Grammar and columns: vectors/README.md.
 */
import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { loads as parse } from 'ison-parser';
import { ISONGraph } from './index.js';

const VECTORS = resolve(dirname(fileURLToPath(import.meta.url)), '..', '..', 'vectors');
const PORT = 'js';

const read = (rel) => readFileSync(resolve(VECTORS, rel), 'utf8');
const rows = parse(read('manifest.ison')).blocks
  .filter((b) => b.kind === 'table' && b.name === 'vectors')
  .flatMap((b) => b.rows);
const load = (rel, text) =>
  rel.endsWith('.isonl') ? ISONGraph.fromIsonl(text) : ISONGraph.fromIson(text);
const emit = (g) => g.toIson() + '\n';

describe('Core Conformance Corpus (js)', () => {
  it('manifest has rows', () => {
    expect(rows.length).toBeGreaterThan(0);
  });

  it('is admitted: no todo in its column', () => {
    expect(rows.filter((r) => r[PORT] === 'todo').map((r) => r.id)).toEqual([]);
  });

  describe.each(rows.map((r) => [r.id, r]))('%s', (_id, row) => {
    it('behaves as the manifest says', () => {
      const expectation = row[PORT];
      const text = read(row.file);

      if (expectation.startsWith('reject:')) {
        let name = '';
        try {
          load(row.file, text);
        } catch (e) {
          name = e.name ?? e.constructor.name;
        }
        expect(name).toBe(expectation.slice('reject:'.length));
        return;
      }

      const g = load(row.file, text);
      expect(g.directed).toBe(row.directed);
      expect(g.nodeCount()).toBe(row.nodes);
      expect(g.edgeCount()).toBe(row.edges);

      const out = emit(g);
      if (expectation === 'defect') {
        // Contradicts the spec (README Findings) - pin what the port does.
        expect(emit(ISONGraph.fromIson(out))).toBe(out);
      } else if (expectation === 'pass') {
        expect(out).toBe(text);
      } else if (expectation === 'pass:canonicalized') {
        expect(out).toBe(read(row.canonical));
        expect(emit(ISONGraph.fromIson(out))).toBe(out);
      } else if (expectation === 'pass:lossy') {
        expect(emit(ISONGraph.fromIson(out))).toBe(out);
      } else {
        throw new Error(`unknown expectation ${JSON.stringify(expectation)} for ${PORT}`);
      }
    });
  });
});
