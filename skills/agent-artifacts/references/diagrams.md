# Diagrams

The engine renders every `diagram` as ASCII, never SVG. Record nodes, edges, labels, and a caption. Never record geometry, colour, or position. Read `code-shaped.md` for the other code-shaped blocks.

Only `plan` and `architecture` accept a `diagram`. Every other kind rejects the field with `schema.unknown-field`. Put the figure in `call_flow`, `call_stacks`, or `file_tree` instead; all eight kinds accept those.

On `architecture` the diagram is required, and its node ids must cover every `components[].id`, or `architecture.diagram-coverage` warns and a strict render fails. Use the component ids as node ids and draw the module graph. The warning offers to let you state why the diagram is scoped, but no field does that, so the only fixes are adding the node or dropping the component. In practice this caps an architecture at the roughly eight components you are willing to draw, whatever `maxItems` allows.

Use a diagram when it makes a mechanism, boundary, dependency, sequence, or ownership relationship easier to understand than prose alone.

The semantic diagram contract contains only meaning:

```json
{
  "title": "Request path",
  "nodes": [
    {"id": "api", "label": "API", "description": "Accepts the request", "status": "current"},
    {"id": "session", "label": "Session lookup", "description": "Binds actor and resource", "status": "new"}
  ],
  "edges": [
    {"from": "api", "to": "session", "label": "authorizes"}
  ],
  "caption": "Authorization happens during lookup before the domain operation runs."
}
```

Do not provide coordinates, dimensions, colours, or SVG. The renderer owns geometry and responsive variants.

The engine derives orientation and edge weight from the graph. Every presentation key - `width`, `height`, `color`, `theme`, `font`, `radius`, `shadow`, `x`, `y` - is rejected as `schema.unknown-field`. Express emphasis through node `status` and edge `label`.

Rules:

- Keep the figure scoped to the claim made in its section.
- Use stable node IDs and valid edge references.
- Keep node labels short; put nuance in `description`. `status` is one of `neutral`, `current`, `new`, `external`, `risk`, `deprecated`.
- Omit `layer`. The engine derives it from the edges, and that ordering is almost always the one you want. Nodes sharing a layer are listed alphabetically by `id`, so two nodes on one layer can print out of flow order, and they disable the single-column chain rendering.
- Explain the complete path in prose or a caption.
- Do not use a decorative diagram to fill space.
- Split a diagram when one figure needs more than roughly eight nodes to remain legible.
