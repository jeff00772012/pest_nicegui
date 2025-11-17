# main.py
from nicegui import ui
import datetime as dt
import pandas as pd

from pest_core import run_pipeline  # reuse the earlier core PEST logic


# ---------- Helper to render the results ----------

def render_results(company: str, df: pd.DataFrame, snapshots: dict):
    result_area.clear()

    if df.empty:
        with result_area:
            ui.notification('No articles found. Try more days or another company.')
        return

    with result_area:
        ui.label(f'PEST Analysis — {company}').classes('text-2xl font-bold')
        ui.label(f'Generated on: {dt.date.today().isoformat()}').classes('text-sm text-gray-500 mb-4')

        # Overview cards
        with ui.row().classes('w-full'):
            for factor in ['Political', 'Economic', 'Social', 'Technological']:
                count = int((df['pest'] == factor).sum())
                with ui.card().classes('w-1/4 items-center'):
                    ui.label(factor).classes('text-lg font-semibold')
                    ui.label(str(count)).classes('text-2xl font-bold')

        # Factor sections
        ui.separator()
        ui.label('Snapshots').classes('text-xl font-semibold mt-4 mb-2')

        for factor in ['Political', 'Economic', 'Social', 'Technological']:
            with ui.expansion(f'{factor} — summary', icon='description', value=True):
                ui.markdown(snapshots.get(factor, '_No clear signals found._'))
                sub = df[df['pest'] == factor].head(8)
                if not sub.empty:
                    ui.label('Key recent items:').classes('mt-2 font-semibold')
                    for _, row in sub.iterrows():
                        when = row['published'][:10] if isinstance(row['published'], str) and row['published'] else ''
                        src = f" — {row['source']}" if row['source'] else ''
                        ui.link(
                            f"{row['title']} ({when}{src})",
                            row['link'],
                            new_tab=True,
                        ).classes('block text-sm')

        ui.separator()
        ui.label('Sources').classes('text-xl font-semibold mt-4 mb-2')

        # Table of sources
        cols = [
            {'name': 'pest', 'label': 'Factor', 'field': 'pest'},
            {'name': 'title', 'label': 'Title', 'field': 'title'},
            {'name': 'source', 'label': 'Source', 'field': 'source'},
            {'name': 'published', 'label': 'Published', 'field': 'published'},
            {'name': 'link', 'label': 'Link', 'field': 'link'},
            {'name': 'query', 'label': 'Query', 'field': 'query'},
        ]
        rows = df.to_dict('records')
        ui.table(columns=cols, rows=rows).classes('w-full')

        # Optional: give markdown text to copy
        ui.separator()
        ui.label('Markdown export (copy-paste)').classes('text-lg font-semibold mt-4')
        ui.textarea(
            value=make_markdown(company, df, snapshots),
        ).props('autogrow readonly')

def make_markdown(company: str, df: pd.DataFrame, snapshots: dict) -> str:
    today = dt.date.today().isoformat()
    lines = [f"# PEST Analysis — {company}", f"_Generated on: {today}_", ""]
    for factor in ['Political', 'Economic', 'Social', 'Technological']:
        lines.append(f"## {factor}")
        lines.append(snapshots.get(factor, "_No clear signals found._"))
        lines.append("")
        sub = df[df['pest'] == factor].head(8).to_dict('records')
        if sub:
            lines.append("**Key recent items:**")
            for a in sub:
                when = a['published'][:10] if isinstance(a['published'], str) and a['published'] else ''
                src = f" — {a['source']}" if a['source'] else ''
                lines.append(f"- [{a['title']}]({a['link']}) ({when}{src})")
            lines.append("")
    lines.append('---')
    lines.append(f"_Sources: {len(df)} articles collected._")
    return '\n'.join(lines)


# ---------- UI layout ----------

ui.page_title('PEST Analyzer (NiceGUI)')

with ui.header().classes('items-center justify-between'):
    ui.label('🧭 PEST Analyzer (NiceGUI)').classes('text-xl font-semibold')
    ui.label('News-based PEST snapshots — open from your iPad browser')

with ui.row().classes('w-full p-4'):
    with ui.card().classes('w-1/4 min-w-[280px]'):
        ui.label('Settings').classes('text-lg font-semibold')

        company_input = ui.input('Company name', value='NVIDIA').classes('w-full')

        days_input = ui.number(
            'Lookback (days)',
            value=14,
            min=1,
            max=60,
            step=1,
        ).classes('w-full')

        max_articles_input = ui.number(
            'Max articles',
            value=60,
            min=20,
            max=200,
            step=10,
        ).classes('w-full')

        async def on_run_click():
            company = company_input.value.strip()
            if not company:
                ui.notification('Please enter a company name.')
                return

            with ui.dialog() as dialog, ui.card():
                ui.label('Running analysis… This may take a little while.')
            dialog.open()

            try:
                df, picks, snapshots = run_pipeline(
                    company=company,
                    days=int(days_input.value),
                    max_articles=int(max_articles_input.value),
                )
                render_results(company, df, snapshots)
            finally:
                dialog.close()

        ui.button('Run analysis', on_click=on_run_click).props('color=primary').classes('mt-2')

    # Area where results appear
    result_area = ui.column().classes('w-3/4 p-4')


import os

port = int(os.getenv("PORT", "8080"))
ui.run(host="0.0.0.0", port=port, reload=False)