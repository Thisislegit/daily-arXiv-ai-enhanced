import os
import json
import logging
import time
from serpapi import GoogleSearch

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def enhance_paper_with_scholar(paper_data):
    """
    Enhance a single paper data using Google Scholar API via SerpApi.
    
    Args:
        paper_data (dict): Dictionary containing paper info (title, authors, etc.)
        
    Returns:
        dict: Enhanced paper data, or original data if enhancement fails.
    """
    api_key = os.getenv("SERP_API_KEY")
    if not api_key:
        logger.warning("SERP_API_KEY not found. Skipping enhancement.")
        return paper_data

    title = paper_data.get("title", "")
    if not title:
        return paper_data

    logger.info(f"Searching Google Scholar for: {title}")

    params = {
        "api_key": api_key,
        "engine": "google_scholar",
        "q": title,
        "hl": "en", # Use English to get standard fields
        "num": 1    # We only need the top result
    }

    try:
        search = GoogleSearch(params)
        results = search.get_dict()
        
        if "error" in results:
            logger.error(f"SerpApi error: {results['error']}")
            return paper_data

        if "organic_results" not in results or not results["organic_results"]:
            logger.warning(f"No results found for: {title}")
            return paper_data

        # Get the best match (first result)
        best_match = results["organic_results"][0]
        
        # Verify if it's likely the same paper (simple title check or author check could be added here)
        # For now, we trust the search engine's top result for the exact title query
        
        # Extract info
        scholar_info = {}
        scholar_info["snippet"] = best_match.get("snippet", "")
        scholar_info["publication_info"] = best_match.get("publication_info", {}).get("summary", "")
        scholar_info["result_id"] = best_match.get("result_id", "")
        scholar_info["link"] = best_match.get("link", "")
        
        # Update paper data
        # We append the snippet to existing summary or replace it if it's just a placeholder
        current_summary = paper_data.get("summary", "")
        new_snippet = scholar_info["snippet"]
        
        if "Abstract not available" in current_summary or len(current_summary) < len(new_snippet):
             paper_data["summary"] = new_snippet
        
        # Add publication info to comment or details
        pub_info = scholar_info["publication_info"]
        if pub_info:
            current_comment = paper_data.get("comment", "")
            if current_comment:
                paper_data["comment"] = f"{current_comment} | {pub_info}"
            else:
                paper_data["comment"] = pub_info

        # If original didn't have a link (or was just a redirect), update it
        if scholar_info["link"]:
            paper_data["url"] = scholar_info["link"]
            
        # Add a flag indicating it was enhanced
        paper_data["scholar_enhanced"] = True
        logger.info(f"Successfully enhanced paper: {title}")
        
    except Exception as e:
        logger.error(f"Failed to enhance paper {title}: {e}")
        
    return paper_data

def enhance_papers_batch(papers):
    """
    Enhance a list of papers.
    """
    enhanced_papers = []
    for paper in papers:
        # Respect rate limits if necessary, though SerpApi handles some queuing.
        # Adding a small delay to be safe and polite if processing many.
        enhanced = enhance_paper_with_scholar(paper)
        enhanced_papers.append(enhanced)
        # time.sleep(0.5) 
    return enhanced_papers

# enhance_papers_batch([{"title": "An optimizing spatial learned index for balanced update and query performance"}])