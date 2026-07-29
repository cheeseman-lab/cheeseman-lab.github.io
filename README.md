# Cheeseman Lab Website

Source for the [Cheeseman Lab](https://cheesemanlab.wi.mit.edu) website — a
[Jekyll](https://jekyllrb.com/) static site studying kinetochore biology and
chromosome segregation at MIT's Whitehead Institute.

The site is deployed via **GitHub Pages**: pushing to `main` rebuilds and
publishes automatically. The custom domain is set in [`CNAME`](CNAME).

## Layout

| Path | What it holds |
|------|---------------|
| `_pages/` | The content pages (`research`, `publications`, `resources`, `team`, `contact`) |
| `_data/` | Structured content — `publications.yml` and `team.yml` — rendered by the pages |
| `_layouts/`, `_includes/` | Page templates and shared partials |
| `assets/` | Images, CSS, and other static assets |
| `scripts/` | Maintenance tooling (see below) |
| `_config.yml` | Jekyll site configuration |

## Updating publications

`_data/publications.yml` drives the Publications page. Refresh it with the
fetch script, which pulls the full author record from OpenAlex (primary) and
PubMed (secondary), drops datasets/meeting abstracts, and de-duplicates
preprints against their published versions:

```bash
conda activate cheeseman-lab
python scripts/fetch_publications.py
```

See [`scripts/README.md`](scripts/README.md) for details.

**Note:** brand-new papers often appear in PubMed before OpenAlex links them to
the author record, so the script may temporarily list a paper as a preprint or
with abbreviated author names. Review the diff after running and hand-correct
those entries until the indexes catch up.

## Local development

If you already have a Ruby toolchain with Bundler:

```bash
bundle install
bundle exec jekyll serve
```

Then open <http://localhost:4000>. Edits to `_data/`, `_pages/`, and layouts
reload on save (a `_config.yml` change needs a restart).

First-time Ruby/Jekyll setup (e.g. via conda):

```bash
conda create -n website
conda activate website
conda install -c conda-forge ruby compilers
gem install bundler jekyll
bundle install
```
