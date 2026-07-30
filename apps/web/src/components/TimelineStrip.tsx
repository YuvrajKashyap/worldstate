const moments = [
  { label: "Live", time: "now", active: true },
  { label: "Observation", time: "-00:12", active: false },
  { label: "Change", time: "-02:41", active: false },
] as const;

export function TimelineStrip() {
  return (
    <section className="timeline" aria-label="Scene history">
      <div className="timeline__intro">
        <p className="eyebrow">Scene time</p>
        <p>History becomes available after the first observation.</p>
      </div>
      <div className="timeline__track">
        {moments.map((moment) => (
          <button
            className="timeline__moment"
            data-active={moment.active}
            disabled={!moment.active}
            key={moment.label}
            type="button"
          >
            <span>{moment.label}</span>
            <time>{moment.time}</time>
          </button>
        ))}
      </div>
    </section>
  );
}
