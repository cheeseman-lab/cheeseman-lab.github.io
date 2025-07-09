import requests
import json
import yaml
import time
import re
from typing import List, Dict, Optional
from difflib import SequenceMatcher

class CleanedSemanticScholarRetriever:
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key
        self.base_url = "https://api.semanticscholar.org/graph/v1"
        self.headers = {
            'Accept': 'application/json'
        }
        
        if api_key:
            self.headers['x-api-key'] = api_key
    
    def get_author_info(self, author_id: str) -> Optional[Dict]:
        """Get author information"""
        url = f"{self.base_url}/author/{author_id}"
        
        params = {
            'fields': 'authorId,name,affiliations,homepage,paperCount,citationCount,hIndex'
        }
        
        try:
            response = requests.get(url, headers=self.headers, params=params)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"Error getting author info: {e}")
            return None
    
    def get_author_papers_batch(self, author_id: str, batch_size: int = 100) -> List[Dict]:
        """Get papers in batches to avoid rate limits"""
        all_papers = []
        offset = 0
        
        while True:
            url = f"{self.base_url}/author/{author_id}/papers"
            
            params = {
                'offset': offset,
                'limit': batch_size,
                'fields': 'paperId,title,authors,venue,year,citationCount,influentialCitationCount,publicationVenue,publicationDate,abstract,externalIds,publicationTypes'
            }
            
            print(f"Getting papers {offset}-{offset + batch_size}...")
            
            max_retries = 3
            batch_papers = None
            
            for attempt in range(max_retries):
                try:
                    response = requests.get(url, headers=self.headers, params=params, timeout=30)
                    
                    if response.status_code == 200:
                        batch_data = response.json()
                        batch_papers = batch_data.get('data', [])
                        break
                    elif response.status_code == 429:
                        # Rate limited - wait longer
                        delay = 10 * (2 ** attempt)  # 10, 20, 40 seconds
                        print(f"Rate limited. Waiting {delay} seconds...")
                        time.sleep(delay)
                        continue
                    else:
                        response.raise_for_status()
                        
                except requests.exceptions.RequestException as e:
                    print(f"Error on attempt {attempt + 1}: {e}")
                    if attempt < max_retries - 1:
                        delay = 10 * (2 ** attempt)
                        print(f"Waiting {delay} seconds before retry...")
                        time.sleep(delay)
                    else:
                        print(f"Failed to get batch after {max_retries} attempts")
                        return all_papers
            
            if not batch_papers:
                break
            
            all_papers.extend(batch_papers)
            print(f"Retrieved {len(batch_papers)} papers in this batch. Total: {len(all_papers)}")
            
            # If we got fewer papers than requested, we've reached the end
            if len(batch_papers) < batch_size:
                break
            
            offset += batch_size
            
            # Rate limiting between requests
            time.sleep(2)  # Wait 2 seconds between batches
        
        return all_papers
    
    def clean_title(self, title: str) -> str:
        """Clean and normalize paper title"""
        if not title:
            return ""
        
        # Remove extra whitespace and normalize
        title = re.sub(r'\s+', ' ', title.strip())
        
        # Remove common artifacts
        title = re.sub(r'^(JCB:|REPORT|Editorial Board|Faculty Opinions recommendation of|Author response:|Decision letter:)', '', title)
        title = re.sub(r'\[An interview by.*?\]\.?$', '', title)
        title = re.sub(r'Citation$', '', title)
        title = re.sub(r'Material Supplemental$', '', title)
        
        # Remove trailing dots and spaces
        title = title.rstrip('. ')
        
        return title
    
    def clean_journal(self, paper: Dict) -> str:
        """Extract and clean journal name"""
        # Try different sources for journal name
        journal = ''
        
        # Try venue first
        venue = paper.get('venue', '')
        if venue:
            journal = venue
        else:
            # Try publicationVenue
            pub_venue = paper.get('publicationVenue', {})
            if pub_venue and pub_venue.get('name'):
                journal = pub_venue['name']
        
        # Clean up journal name
        if journal:
            # Remove common artifacts
            journal = re.sub(r'\(Dutch-Flemish ed\. Print\)', '', journal)
            journal = re.sub(r'\s+', ' ', journal.strip())
        
        return journal
    
    def clean_authors(self, authors: List[Dict]) -> List[str]:
        """Clean and format author names"""
        cleaned_authors = []
        
        for author in authors:
            name = author.get('name', '').strip()
            if not name:
                continue
            
            # Skip obviously bad author entries
            if len(name) > 100:  # Suspiciously long names
                continue
            
            # Normalize "I. Cheeseman" variants
            if 'cheeseman' in name.lower():
                if name.lower() in ['i. cheeseman', 'iain cheeseman', 'iain m cheeseman', 'cheeseman im', 'cheeseman i']:
                    name = 'I. Cheeseman'
            
            cleaned_authors.append(name)
        
        return cleaned_authors
    
    def is_valid_publication(self, paper: Dict) -> bool:
        """Check if this is a valid scientific publication"""
        title = self.clean_title(paper.get('title', ''))
        
        # Skip if no title
        if not title:
            return False
        
        # Skip very short titles (likely artifacts)
        if len(title) < 10:
            return False
        
        # Skip certain publication types
        pub_types = paper.get('publicationTypes', [])
        if pub_types:
            skip_types = ['Editorial', 'News', 'LettersAndComments', 'ClinicalTrial']
            if any(pt in skip_types for pt in pub_types):
                return False
        
        # Skip titles that are clearly not research papers
        skip_patterns = [
            r'^Editorial Board',
            r'^Faculty Opinions recommendation',
            r'^Author response:',
            r'^Decision letter:',
            r'Crystal structure.*pdb$',
            r'Structure of.*pdb$',
            r'^\d{4}\.\d{4}/.*',  # PDB IDs
            r'Material Supplemental',
            r'Citation$'
        ]
        
        for pattern in skip_patterns:
            if re.search(pattern, title, re.IGNORECASE):
                return False
        
        # Skip if journal is empty or suspicious
        journal = self.clean_journal(paper)
        if not journal or journal in ['', 'Clinical neurology and neurosurgery (Dutch-Flemish ed. Print)']:
            # Allow empty journal for bioRxiv/preprints
            if 'biorxiv' not in title.lower():
                return False
        
        return True
    
    def similarity(self, title1: str, title2: str) -> float:
        """Calculate similarity between two titles"""
        return SequenceMatcher(None, title1.lower(), title2.lower()).ratio()
    
    def remove_duplicates(self, publications: List[Dict]) -> List[Dict]:
        """Remove duplicate publications based on title similarity"""
        unique_publications = []
        seen_titles = set()
        
        for pub in publications:
            title = pub['title'].lower().strip()
            
            # Check for exact matches first
            if title in seen_titles:
                continue
            
            # Check for near-duplicates
            is_duplicate = False
            for existing_pub in unique_publications:
                existing_title = existing_pub['title'].lower().strip()
                
                # Check similarity
                sim = self.similarity(title, existing_title)
                
                # Consider duplicates if very similar (>0.9) or if one title contains the other
                if sim > 0.9 or title in existing_title or existing_title in title:
                    is_duplicate = True
                    
                    # Keep the one with more complete information
                    if (pub.get('publication_year') and not existing_pub.get('publication_year')) or \
                       (pub.get('doi') and not existing_pub.get('doi')) or \
                       (pub.get('journal') and not existing_pub.get('journal')):
                        # Replace existing with current (more complete)
                        unique_publications.remove(existing_pub)
                        seen_titles.discard(existing_title)
                        is_duplicate = False
                    
                    break
            
            if not is_duplicate:
                unique_publications.append(pub)
                seen_titles.add(title)
        
        return unique_publications
    
    def extract_publication_info(self, paper: Dict) -> Optional[Dict]:
        """Extract and clean publication information"""
        try:
            # Clean title
            title = self.clean_title(paper.get('title', ''))
            if not title:
                return None
            
            # Clean authors
            authors = self.clean_authors(paper.get('authors', []))
            
            # Clean journal
            journal = self.clean_journal(paper)
            
            # Get publication year
            pub_year = paper.get('year')
            
            # Get DOI
            doi = ''
            external_ids = paper.get('externalIds', {})
            if external_ids and external_ids.get('DOI'):
                doi = external_ids['DOI']
            
            return {
                'title': title,
                'authors': authors,
                'journal': journal,
                'publication_year': pub_year,
                'doi': doi,
                'citation_count': paper.get('citationCount', 0),
                'semantic_scholar_id': paper.get('paperId', '')
            }
            
        except Exception as e:
            print(f"Error extracting publication info: {e}")
            return None
    
    def get_cheeseman_publications(self) -> List[Dict]:
        """Get cleaned publications for Iain Cheeseman"""
        print("=== Getting Cheeseman Publications ===")
        
        # Iain Cheeseman's Semantic Scholar Author ID
        cheeseman_author_id = "6333519"
        
        # Get author info
        print(f"Getting author info for ID: {cheeseman_author_id}")
        author_info = self.get_author_info(cheeseman_author_id)
        
        if author_info:
            print(f"Author: {author_info.get('name', 'N/A')}")
            print(f"Paper count: {author_info.get('paperCount', 'N/A')}")
            print(f"Citation count: {author_info.get('citationCount', 'N/A')}")
        
        # Wait a bit after getting author info to avoid rate limit
        print("Waiting 3 seconds before getting papers...")
        time.sleep(3)
        
        # Get papers in batches
        print(f"\nGetting papers for author ID: {cheeseman_author_id}")
        papers = self.get_author_papers_batch(cheeseman_author_id, batch_size=50)  # Smaller batches
        
        if not papers:
            print("No papers found")
            return []
        
        print(f"Found {len(papers)} raw papers")
        
        # Filter valid publications
        valid_papers = [paper for paper in papers if self.is_valid_publication(paper)]
        print(f"After filtering: {len(valid_papers)} valid papers")
        
        return valid_papers
    
    def process_publications(self, papers: List[Dict]) -> List[Dict]:
        """Process and clean publications"""
        publications = []
        
        print("Processing publications...")
        for paper in papers:
            pub_info = self.extract_publication_info(paper)
            if pub_info and pub_info['title']:
                publications.append(pub_info)
        
        print(f"Extracted {len(publications)} publications")
        
        # Remove duplicates
        print("Removing duplicates...")
        unique_publications = self.remove_duplicates(publications)
        print(f"After deduplication: {len(unique_publications)} unique publications")
        
        # Sort by year (newest first), then by citation count
        unique_publications.sort(
            key=lambda x: (
                x.get('publication_year') or 0, 
                x.get('citation_count') or 0
            ), 
            reverse=True
        )
        
        return unique_publications
    
    def save_to_yaml(self, publications: List[Dict], filename: str = 'publications.yml') -> None:
        """Save publications to YAML file (clean format for website)"""
        clean_publications = []
        for pub in publications:
            clean_pub = {
                'title': pub['title'],
                'authors': pub['authors'],
                'journal': pub['journal'],
                'publication_year': pub['publication_year'],
                'doi': pub['doi']
            }
            clean_publications.append(clean_pub)
        
        with open(filename, 'w', encoding='utf-8') as f:
            yaml.dump(clean_publications, f, 
                     default_flow_style=False,
                     allow_unicode=True,
                     sort_keys=False)
        
        print(f"Clean publications saved to {filename}")
    
    def save_detailed_json(self, publications: List[Dict], filename: str = 'publications_detailed.json') -> None:
        """Save detailed publications with all metadata to JSON"""
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(publications, f, indent=2, ensure_ascii=False)
        
        print(f"Detailed publications saved to {filename}")
    
    def print_summary(self, publications: List[Dict]) -> None:
        """Print a summary of retrieved publications"""
        if not publications:
            print("No publications found.")
            return
        
        print(f"\n=== PUBLICATION SUMMARY ===")
        print(f"Total publications: {len(publications)}")
        
        # Year distribution
        years = [p.get('publication_year') for p in publications if p.get('publication_year') is not None]
        if years:
            print(f"Year range: {min(years)} - {max(years)}")
            
            no_year_count = len([p for p in publications if p.get('publication_year') is None])
            if no_year_count > 0:
                print(f"Papers without publication year: {no_year_count}")
        
        # Citation stats
        citations = [p.get('citation_count') or 0 for p in publications]
        if citations:
            total_citations = sum(citations)
            print(f"Total citations: {total_citations}")
            print(f"Average citations per paper: {total_citations / len(citations):.1f}")
            print(f"Most cited paper: {max(citations)} citations")
        
        # Top journals
        journals = [p.get('journal') for p in publications if p.get('journal')]
        journal_counts = {}
        for journal in journals:
            journal_counts[journal] = journal_counts.get(journal, 0) + 1
        
        if journal_counts:
            print(f"\nTop 5 journals:")
            for journal, count in sorted(journal_counts.items(), key=lambda x: x[1], reverse=True)[:5]:
                print(f"  {journal}: {count} papers")
        
        # Recent papers
        papers_with_years = [p for p in publications if p.get('publication_year') is not None]
        papers_without_years = [p for p in publications if p.get('publication_year') is None]
        
        print(f"\n5 Most recent papers:")
        display_papers = papers_with_years[:5] if len(papers_with_years) >= 5 else papers_with_years + papers_without_years[:5-len(papers_with_years)]
        
        for i, pub in enumerate(display_papers):
            year_str = pub.get('publication_year') or 'N/A'
            print(f"  {i+1}. {pub['title']} ({year_str})")
            print(f"     Journal: {pub.get('journal') or 'N/A'}")
            print(f"     Citations: {pub.get('citation_count') or 'N/A'}")
            print()

# Usage example
if __name__ == "__main__":
    # Initialize retriever
    retriever = CleanedSemanticScholarRetriever(api_key=None)
    
    # Get Cheeseman lab publications
    papers = retriever.get_cheeseman_publications()
    
    if papers:
        # Process publications (includes deduplication)
        publications = retriever.process_publications(papers)
        
        # Print summary
        retriever.print_summary(publications)
        
        # Save to files
        retriever.save_to_yaml(publications)
        retriever.save_detailed_json(publications)
        
        print(f"\nSuccessfully retrieved {len(publications)} cleaned, deduplicated publications!")
    else:
        print("No publications found")