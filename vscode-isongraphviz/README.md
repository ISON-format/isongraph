# ISONGraph Viz

Deterministic graph visualization for `.ison` property graphs inside VS Code.

Open a `.ison` graph file and run **ISONGraph Viz: Visualize Graph** (or click
the graph icon in the editor title bar).

## How it works

The same three stages as the `ison_graph.viz` Python module:

1. **Data** — the `.ison` file is parsed into nodes and edges.
2. **Layout** — a seeded Fruchterman–Reingold force simulation assigns every
   node an `(x, y)` coordinate. The layout algorithm and PRNG are exact
   mirrors of `ison_graph.viz.compute_layout`, so the same graph and seed
   produce **identical geometry** here and in a Python-rendered SVG.
3. **Rendering** — the coordinates are drawn to SVG in a webview: nodes
   colored by type (colorblind-safe palette), sized by degree, with a legend,
   arrowheads, and hover tooltips.

On top of the deterministic layout there is a **live physics** layer: drag any
node and its neighbors relax around it with an animated low-temperature force
simulation. *Reset layout* snaps everything back to the seeded geometry;
*Fit* resets pan/zoom; the *Live physics* checkbox disables the animation
entirely (dragging then moves only the grabbed node).

The visualizer re-renders automatically as you edit the file.

## Settings

| Setting | Default | Description |
|---------|---------|-------------|
| `isongraphviz.seed` | `42` | Layout seed — same graph + same seed = same picture |
| `isongraphviz.iterations` | `170` | Iterations for the initial deterministic layout |

## Zero dependencies

No bundled libraries, no CDN scripts — the layout and renderer are ~400 lines
of plain JavaScript, and the webview's Content-Security-Policy blocks all
remote resources. Works fully offline.

## Development

```bash
npm install
npm run compile
# then press F5 in VS Code to launch the Extension Development Host
```

## License

MIT — part of the [ISONGraph](https://github.com/ISON-format/isongraph) project.
