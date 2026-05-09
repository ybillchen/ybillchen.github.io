#!/usr/bin/env python3
"""
Fetch papers from ADS/SciX and generate publications_live.html.

Required env vars:
  ADS_TOKEN            — from scixplorer.org/user/settings/token
Optional env vars:
  MAIN_LIBRARY_ID      — defaults to the hardcoded value below
  STUDENTS_LIBRARY_ID  — leave unset to skip supervised-students section
"""

import html as html_module
import os
import re
import sys

import requests

ADS_BASE            = 'https://api.adsabs.harvard.edu/v1'
ADS_TOKEN           = os.environ.get('ADS_TOKEN', '')
MAIN_LIBRARY_ID     = os.environ.get('MAIN_LIBRARY_ID', 'F1MRsWjEQSaE5bmKO_L1Ag')
STUDENTS_LIBRARY_ID = os.environ.get('STUDENTS_LIBRARY_ID', 'ksvXbt1JQmWJ0MSlHoamRQ')
MY_NAME_RE          = re.compile(r'chen,\s*yingtian', re.IGNORECASE)
MAX_AUTHORS         = 8
OUT_PATH            = os.path.join(os.path.dirname(__file__), '..', 'publications_live.html')

HEADERS = lambda: {'Authorization': f'Bearer {ADS_TOKEN}'}


# ── ADS API calls ──────────────────────────────────────────────────────────────

def fetch_library(library_id):
    r = requests.get(f'{ADS_BASE}/biblib/libraries/{library_id}',
                     headers=HEADERS(), timeout=30)
    r.raise_for_status()
    return r.json().get('documents', [])


def fetch_metadata(bibcodes):
    body = 'bibcode\n' + '\n'.join(bibcodes)
    r = requests.post(
        f'{ADS_BASE}/search/bigquery',
        params={
            'q': '*',
            'fl': 'bibcode,title,author,year,pub,bibstem,volume,page,doi,identifier',
            'rows': 200,
            'sort': 'date desc',
        },
        headers={**HEADERS(), 'Content-Type': 'big-query/csv'},
        data=body.encode('utf-8'),
        timeout=30,
    )
    r.raise_for_status()
    return r.json().get('response', {}).get('docs', [])


# ── Formatting helpers ─────────────────────────────────────────────────────────

def ads_to_display_name(ads_name):
    """Convert 'Last, First M.' → 'First M. Last'."""
    parts = ads_name.split(',', 1)
    if len(parts) == 2:
        return f'{parts[1].strip()} {parts[0].strip()}'
    return ads_name


def format_citation(paper):
    stem_list = paper.get('bibstem', [])
    stem = stem_list[0] if stem_list else paper.get('pub', '')
    vol  = paper.get('volume', '')
    page_list = paper.get('page', [])
    pg   = page_list[0] if page_list else ''
    if vol and pg:
        return f'{stem} <b>{vol}</b>, {pg}'
    if vol:
        return f'{stem} <b>{vol}</b>'
    if stem.lower() == 'arxiv':
        return 'preprint'
    return paper.get('pub', stem)


def extract_arxiv_id(identifiers):
    for ident in (identifiers or []):
        if ident.lower().startswith('arxiv:'):
            return ident[6:]
    return None


def render_buttons(paper):
    parts = [
        f'<a rel="noopener noreferrer" target="_blank" '
        f'href="https://scixplorer.org/abs/{paper["bibcode"]}" '
        f'class="btn" role="button">SciX</a>'
    ]
    arxiv = extract_arxiv_id(paper.get('identifier'))
    if arxiv:
        parts.append(
            f'<a rel="noopener noreferrer" target="_blank" '
            f'href="https://arxiv.org/abs/{arxiv}" class="btn" role="button">arXiv</a>'
        )
    doi_list = paper.get('doi') or []
    if doi_list:
        parts.append(
            f'<a rel="noopener noreferrer" target="_blank" '
            f'href="https://doi.org/{doi_list[0]}" class="btn" role="button">Publisher</a>'
        )
    return '\n                '.join(parts)


def render_authors(authors, is_first_author):
    if not authors:
        return ''
    shown  = authors[:MAX_AUTHORS]
    et_al  = len(authors) > MAX_AUTHORS
    parts  = []
    for i, a in enumerate(shown):
        is_me   = bool(MY_NAME_RE.search(a))
        display = html_module.escape(ads_to_display_name(a))
        if is_me:
            icon = (
                '<img border="0" src="figs/mail.svg" width=24px '
                'style="vertical-align: top;">'
                if i == 0 and is_first_author else ''
            )
            parts.append(f'<b>{display}</b>{icon}')
        else:
            parts.append(display)
    result = ', '.join(parts)
    if et_al:
        result += ', et al.'
    return result


def render_paper(paper, is_first_author):
    authors_html = render_authors(paper.get('author', []), is_first_author)
    citation     = format_citation(paper)
    buttons      = render_buttons(paper)
    title_list   = paper.get('title') or ['(no title)']
    title        = html_module.escape(title_list[0])
    year         = paper.get('year', '')
    return (
        f'            <li><p><div class="row">\n'
        f'              <div class="col-lg-8">\n'
        f'                {authors_html} ({year}),\n'
        f'                <i>{title}</i>,\n'
        f'                {citation}.\n'
        f'              </div>\n'
        f'              <div class="col-lg-4">\n'
        f'                {buttons}\n'
        f'              </div>\n'
        f'            </div></p></li>'
    )


# ── HTML generation ────────────────────────────────────────────────────────────

def generate_html(first_author, students, contributing):
    total = len(first_author) + len(students) + len(contributing)
    first_items       = '\n'.join(render_paper(p, True)  for p in first_author)
    student_items     = '\n'.join(render_paper(p, False) for p in students)
    contributing_items = '\n'.join(render_paper(p, False) for p in contributing)

    student_start      = len(first_author) + 1
    contributing_start = student_start + len(students)

    student_section = (
        f'\n    <div id="student-section" class="section">\n'
        f'      <div class="container">\n'
        f'        <div class="col-lg-8 offset-lg-2">\n'
        f'          <h1>Publications by *(co-)supervised students</h1>\n'
        f'          <ol start="{student_start}">\n'
        f'{student_items}\n'
        f'          </ol>\n'
        f'        </div>\n'
        f'      </div>\n'
        f'    </div>\n'
    ) if students else ''

    return f"""\
<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <meta name="keywords" content="">
    <meta name="description" content="">
    <meta name="author" content="Bill Chen">
    <title>Bill Chen — Publications</title>

    <link href="figs/icon.svg" rel="icon">
    <link href="figs/icon.svg" rel="apple-touch-icon">

    <link href="bootstrap/bootstrap.css" rel="stylesheet">
    <link href="css/style.css" rel="stylesheet">
  </head>

  <body class="d-flex flex-column min-vh-100">

    <nav class="navbar fixed-top navbar-expand-md">
      <div class="container">
        <button class="navbar-toggler ms-auto" type="button" data-bs-toggle="collapse" data-bs-target="#navbarSupportedContent" aria-controls="navbarSupportedContent" aria-expanded="false" aria-label="Toggle navigation">
          <img src="figs/list.svg" alt="menu" width="30px">
        </button>
        <div class="collapse navbar-collapse justify-content-center" id="navbarSupportedContent">
          <ul class="navbar-nav">
            <a class="nav-link" href="index.html">Home</a>
            <a class="nav-link" href="research.html">Research</a>
            <a class="nav-link active" href="publications_live.html">Publications</a>
          </ul>
        </div>
      </div>
    </nav>

    <div id="publications" class="first_section">
      <div class="container">
        <div class="col-lg-8 offset-lg-2">
          <h1>Bill's publications</h1>
          <ul>
            <li>
              <b>{total}</b> in total = <b>{len(first_author)}</b> as first author + <b>{len(students)}</b> by (co-)supervised students + <b>{len(contributing)}</b> as contributing author
            </li>
          </ul>
          <div style="padding-left:25px">
            <p>
              <a rel="noopener noreferrer" target="_blank" href="https://scixplorer.org/user/libraries/F1MRsWjEQSaE5bmKO_L1Ag" class="btn" role="button">SciX Library</a>
            </p>
          </div>
        </div>
      </div>
    </div>

    <div id="first-author-section" class="section">
      <div class="container">
        <div class="col-lg-8 offset-lg-2">
          <h1>Publications as first author</h1>
          <ol>
{first_items}
          </ol>
        </div>
      </div>
    </div>
{student_section}
    <div id="contributing-section" class="section">
      <div class="container">
        <div class="col-lg-8 offset-lg-2">
          <h1>Publications as contributing author</h1>
          <ol start="{contributing_start}">
{contributing_items}
          </ol>
          <p>
            <img border="0" src="figs/mail.svg" width=24px style="vertical-align: top;"> Corresponding author
          </p>
        </div>
      </div>
    </div>

    <div id="copyrights" class="mt-auto">
      <div class="container">
        <div class="col-lg-8 offset-lg-2">
          <p>&copy; 2020 &mdash; <span id="year"></span> Bill Chen</p>
        </div>
      </div>
    </div>

    <script src="bootstrap/bootstrap.js"></script>
    <script>
      document.getElementById("year").innerHTML = new Date().getFullYear();
    </script>

  </body>
</html>
"""


# ── Entry point ────────────────────────────────────────────────────────────────

def main():
    if not ADS_TOKEN:
        print('Error: ADS_TOKEN is not set.', file=sys.stderr)
        sys.exit(1)

    print(f'Fetching main library ({MAIN_LIBRARY_ID})...')
    main_bibcodes = fetch_library(MAIN_LIBRARY_ID)
    print(f'  {len(main_bibcodes)} papers')

    student_set = set()
    if STUDENTS_LIBRARY_ID:
        print(f'Fetching students library ({STUDENTS_LIBRARY_ID})...')
        student_bibcodes = fetch_library(STUDENTS_LIBRARY_ID)
        student_set = set(student_bibcodes)
        print(f'  {len(student_bibcodes)} papers')

    print('Fetching metadata...')
    papers = fetch_metadata(main_bibcodes)
    papers.sort(key=lambda p: int(p.get('year') or 0), reverse=True)
    print(f'  {len(papers)} papers returned')

    first_author, students, contributing = [], [], []
    for p in papers:
        if p['bibcode'] in student_set:
            students.append(p)
        elif p.get('author') and MY_NAME_RE.search(p['author'][0]):
            first_author.append(p)
        else:
            contributing.append(p)

    print(f'  first={len(first_author)}, students={len(students)}, contributing={len(contributing)}')

    out = os.path.normpath(OUT_PATH)
    with open(out, 'w', encoding='utf-8') as f:
        f.write(generate_html(first_author, students, contributing))
    print(f'Written: {out}')


if __name__ == '__main__':
    main()
