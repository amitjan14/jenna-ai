"""Presentation-ready timing rows; all durations are measured wall seconds."""

def timing_rows(metrics):
    steps = metrics.get('steps', [])
    by_id = {row['id']: row for row in steps}
    total = metrics.get('total_seconds', 0)
    rows = []
    for step in steps:
        parent = by_id.get(step.get('parent_id'))
        rows.append({
            'Step': step['label'],
            'Within': parent['label'] if parent else '—',
            'Start (s)': round(step['start_seconds'] - steps[0]['start_seconds'], 4),
            'Total (s)': round(step['seconds'], 4),
            'Own (s)': round(step['self_seconds'], 4),
            '% request (own)': round(100 * step['self_seconds'] / total, 1) if total else 0,
            'Status': step['status'],
            'Method': step['method'],
        })
    return rows


def slowest_steps(metrics):
    return sorted(timing_rows(metrics), key=lambda row: row['Own (s)'], reverse=True)
