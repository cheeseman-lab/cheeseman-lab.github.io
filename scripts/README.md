Convert from PubMed. 

Search for Cheeseman IM, Save -> Selection: All results, Format: Abstract. Save in this folder as publications.txt. Run:

```bash
conda activate website
pip install pyyaml
python pubmed_yml.py 
```

Move publications.yml to /_data.