## Fetch Publications

Run `fetch_publications.py` to pull all Cheeseman Lab publications from OpenAlex (primary) + PubMed (secondary). The script writes directly to `/_data/publications.yml`.

```bash
conda activate cheeseman-lab
python fetch_publications.py
```

Outputs:
- `../_data/publications.yml` — website publications data (updated in place)
- `publications_detailed.json` — full metadata with citation counts

Dependencies: `requests`, `pyyaml` (already in the `cheeseman-lab` conda env)
