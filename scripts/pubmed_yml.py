import yaml
import re

def clean_text(text):
    """Clean up text by removing escape characters and merging lines."""
    if not text:
        return text
    cleaned = re.sub(r'\\\s*\n\s*', ' ', text)
    cleaned = re.sub(r'\s+', ' ', cleaned)
    cleaned = cleaned.replace('\\', '')
    cleaned = re.sub(r'^["\'](.*)["\']$', r'\1', cleaned)
    return cleaned.strip()

def parse_authors(author_line):
    """Parse authors from the author line."""
    author_line = author_line.rstrip('.')
    authors = author_line.split(',')
    cleaned_authors = []
    for author in authors:
        author = re.sub(r'\(\d+\)', '', author)
        author = clean_text(author)
        if author:
            cleaned_authors.append(author)
    return cleaned_authors

def parse_citation(text):
    """Parse a citation into structured data."""
    # Initialize with fields in desired order
    pub_data = {
        'title': None,
        'authors': None,
        'journal': None,
        'doi': None,
        'publication_year': None,
        'pubmed_id': None
    }
    
    sections = [s.strip() for s in text.split('\n\n') if s.strip()]
    
    if len(sections) >= 3:
        # Title
        pub_data['title'] = clean_text(sections[1])
        
        # Authors
        author_line = sections[2].strip()
        pub_data['authors'] = parse_authors(author_line)
        
        # Citation info
        citation_line = sections[0]
        
        # Journal
        journal_match = re.match(r'^(.+?)\.\s*\d{4}', citation_line)
        if journal_match:
            pub_data['journal'] = journal_match.group(1).strip()
        
        # DOI
        doi_match = re.search(r'doi:\s*([\d\./\-a-zA-Z]+)', citation_line)
        if doi_match:
            pub_data['doi'] = doi_match.group(1).strip().rstrip('.')
        
        # Year
        year_match = re.search(r'(\d{4})\s+[A-Z][a-z]{2}', citation_line)
        if year_match:
            pub_data['publication_year'] = year_match.group(1)
        
        # PMID
        pmid_match = re.search(r'PMID:\s*(\d+)', text)
        if pmid_match:
            pub_data['pubmed_id'] = pmid_match.group(1)
    
    # Remove None values
    return {k: v for k, v in pub_data.items() if v is not None}

def main():
    with open('publications.txt', 'r', encoding='utf-8') as f:
        content = f.read()
    
    entries = re.split(r'\n\d+\.\s+', content)
    
    publications = []
    for entry in entries[1:]:
        if entry.strip():
            pub_data = parse_citation(entry.strip())
            if pub_data:
                publications.append(pub_data)
    
    with open('publications.yml', 'w', encoding='utf-8') as f:
        yaml.dump(publications, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
    
    print(f"Processed {len(publications)} publications")

if __name__ == "__main__":
    main()