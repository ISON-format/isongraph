/**
 * Core Conformance Corpus runner for the TypeScript port.
 * Reads vectors/manifest.ison with ison-ts and checks the 'ts' column.
 * Grammar and columns: vectors/README.md.
 */
import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { parse } from 'ison-ts';
import { ISONGraph } from './index';

const VECTORS = resolve(dirname(fileURLToPath(import.meta.url)), '..', '..', 'vectors');
const PORT = 'ts';

type Row = Record<string, any>;

const read = (rel: string): string => readFileSync(resolve(VECTORS, rel), 'utf8');
const rows: Row[] = parse(read('manifest.ison')).blocks
  .filter((b: any) => b.kind === 'table' && b.name === 'vectors')
  .flatMap((b: any) => b.rows as Row[]);
const load = (rel: string, text: string): ISONGraph =>
  rel.endsWith('.isonl') ? ISONGraph.fromIsonl(text) : ISONGraph.fromIson(text);
const emit = (g: ISONGraph): string => g.toIson() + '\n';

describe('Core Conformance Corpus (ts)', () => {
  it('manifest has rows', () => {
    expect(rows.length).toBeGreaterThan(0);
  });

  it('is admitted: no todo in its column', () => {
    expect(rows.filter(r => r[PORT] === 'todo').map(r => r.id)).toEqual([]);
  });

  describe.each(rows.map(r => [r.id as string, r] as const))('%s', (_id, row) => {
    it('behaves as the manifest says', () => {
      const expectation = row[PORT] as string;
      const text = read(row.file);

      if (expectation.startsWith('reject:')) {
        let name = '';
        try {
          load(row.file, text);
        } catch (e: any) {
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
        // The loss must be real: if the port now preserves the input, the
        // cell is stale and should become 'pass'.
        expect(out, 'pass:lossy but output equals the file - promote the cell to pass').not.toBe(text);
        expect(emit(ISONGraph.fromIson(out))).toBe(out);
      } else {
        throw new Error(`unknown expectation ${JSON.stringify(expectation)} for ${PORT}`);
      }
    });
  });
});
