import csv
import yaml

def clean_authors(authors_string):
    # Split authors by comma and clean up each name
    authors = [author.strip() for author in authors_string.split(',')]
    # Remove empty authors
    authors = [author for author in authors if author]
    return authors

def convert_csv_to_yaml(input_file, output_file):
    publications = []
    
    with open(input_file, 'r', encoding='utf-8') as file:
        # Skip the header row
        reader = csv.DictReader(file)
        
        for row in reader:
            # Create publication entry with required fields
            publication = {
                'title': row['Title'].strip(),
                'authors': clean_authors(row['Authors']),
                'journal': row['Journal'].strip(),
                'publication_year': int(row['Publication year']),
                'doi': row['DOI'].strip() if row['DOI'] else ''
            }
            
            # Only include if it's a published article (not preprint)
            if row['Item type'] in ['Journal Article', 'Review', 'Commentary']:
                publications.append(publication)
    
    # Sort publications by year (newest first)
    publications.sort(key=lambda x: x['publication_year'], reverse=True)
    
    # Write to YAML file
    with open(output_file, 'w', encoding='utf-8') as file:
        yaml.dump(publications, file,
                 default_flow_style=False,
                 allow_unicode=True,
                 sort_keys=False)

if __name__ == "__main__":
    input_file = "references.csv"  # Your input CSV file
    output_file = "publications.yml"  # Your output YAML file
    convert_csv_to_yaml(input_file, output_file)