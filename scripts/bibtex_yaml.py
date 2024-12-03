import bibtexparser
import yaml
import re

def clean_title(title):
    # Remove LaTeX formatting and unnecessary whitespace
    title = re.sub(r'\{|\}', '', title)
    title = re.sub(r'\s+', ' ', title)
    return title.strip()

def clean_author(author):
    # Remove LaTeX formatting and clean up author names
    author = re.sub(r'\{|\}', '', author)
    author = re.sub(r'\s+', ' ', author)
    
    # Handle special characters and formatting
    author = author.replace('\\', '')
    author = author.replace('{\'a}', 'á')
    author = author.replace('{\'e}', 'é')
    author = author.replace('{\\"o}', 'ö')
    
    return author.strip()

def convert_bibtex_to_yaml():
    # Configure parser to be more lenient with special characters
    parser = bibtexparser.bparser.BibTexParser(common_strings=True)
    parser.customization = lambda record: record
    
    with open('references.bib', encoding='utf-8') as bibtex_file:
        bib_database = bibtexparser.load(bibtex_file, parser=parser)
    
    publications = []
    for entry in bib_database.entries:
        # Skip entries that are marked as unpublished
        if entry.get('ENTRYTYPE', '').lower() == 'unpublished':
            continue
            
        # Clean and process the entry
        authors = [clean_author(author) for author in entry.get('author', '').split(' and ')]
        title = clean_title(entry.get('title', ''))
        
        pub = {
            'title': title,
            'authors': authors,
            'journal': entry.get('journal', ''),
            'publication_year': int(entry.get('year', 0)),
            'doi': entry.get('doi', '')
        }
        publications.append(pub)
    
    # Sort publications by year (newest first)
    publications.sort(key=lambda x: x['publication_year'], reverse=True)
    
    # Write to YAML file
    with open('publications.yml', 'w', encoding='utf-8') as yaml_file:
        yaml.dump(publications, yaml_file, 
                 sort_keys=False, 
                 allow_unicode=True, 
                 default_flow_style=False)

if __name__ == "__main__":
    convert_bibtex_to_yaml()