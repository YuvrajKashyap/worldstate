const foundationLayers = [
  {
    name: "Static world",
    detail: "Geometry that should remain fixed",
    state: "awaiting scan",
  },
  {
    name: "Persistent objects",
    detail: "Movable entities with explicit memory",
    state: "no observations",
  },
  {
    name: "Transient agents",
    detail: "Hands and people excluded from fusion",
    state: "inactive",
  },
  {
    name: "Historical memory",
    detail: "Evidence, state, relationships, and events",
    state: "empty",
  },
] as const;

export function FoundationPanel() {
  return (
    <aside className="foundation-panel" aria-label="World model layers">
      <div className="panel-heading">
        <p className="eyebrow">World model</p>
        <p className="panel-summary">
          Observation and belief remain separate at every layer.
        </p>
      </div>

      <ol className="layer-list">
        {foundationLayers.map((layer) => (
          <li className="layer-row" key={layer.name}>
            <span className="layer-marker" aria-hidden="true" />
            <div>
              <h2>{layer.name}</h2>
              <p>{layer.detail}</p>
            </div>
            <span className="layer-state">{layer.state}</span>
          </li>
        ))}
      </ol>
    </aside>
  );
}
