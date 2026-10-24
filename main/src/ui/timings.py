"""Shared request and upload timing presentation."""
import json
import streamlit as st
from main.src.utils.timing_summary import timing_rows, slowest_steps


def display_timings(metrics, key):
    rows = timing_rows(metrics)
    if not rows:
        return
    with st.expander('Step timings · find the slowest method'):
        slowest = slowest_steps(metrics)
        top = slowest[0]
        st.write(f"Largest own time: **{top['Step']} — {top['Own (s)']:.2f}s** "
                 f"({top['% request (own)']:.1f}% of request)")
        st.caption('Total includes child steps. Own excludes child steps; use Own to compare bottlenecks. '
                   'Repeated calls appear separately. Times exclude browser rendering.')
        flow, bottlenecks, models = st.tabs(['Execution order', 'Slowest methods', 'Model calls'])
        with flow:
            st.dataframe(rows, hide_index=True, width='stretch')
        with bottlenecks:
            st.dataframe(slowest, hide_index=True, width='stretch')
        with models:
            calls = metrics.get('calls', [])
            by_id = {step['id']: step for step in metrics['steps']}
            model_rows = []
            for call in calls:
                span = by_id.get(call.get('span_id'), {})
                parent = by_id.get(span.get('parent_id'), {})
                model_rows.append({
                    'Operation': call['kind'], 'Within': parent.get('label', call.get('label', '—')),
                    'Wall (s)': call['seconds'],
                    'Load (s)': call.get('load_seconds'),
                    'Prompt (s)': call.get('prompt_seconds'),
                    'Generate (s)': call.get('generation_seconds'),
                    'Method': call.get('method', '—'),
                })
            st.dataframe(model_rows, hide_index=True, width='stretch')
            st.caption('Load, prompt and generation times come from Ollama when supplied. '
                       'Blank values are unavailable. Wall time also includes transport and service overhead.')
        st.download_button('Download timing JSON', json.dumps(metrics, indent=2),
                           file_name='jenna-timings.json', mime='application/json', key=f'timings-{key}')
