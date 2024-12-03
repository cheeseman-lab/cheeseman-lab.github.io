Convert from PubMed. 

Search for Cheeseman IM, Save -> Selection: All results, Format: PMID. Go to: https://www.bibtex.com/c/pmid-to-bibtex-converter/. Convert to BibTex/csv, save as references.bib/references.csv in this folder. Then:

```bash
conda activate website
pip install bibtexparser pyyaml
python bibtex_yaml.py 
python bibtex_csv.py # preferred to get doi (link to paper) 
```

Move publications.yml to /_data.