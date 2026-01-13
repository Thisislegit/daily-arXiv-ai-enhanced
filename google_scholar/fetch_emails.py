import imaplib
import email
import os
import sys
import datetime
import argparse
import hashlib
import json
import re
from email.header import decode_header
from bs4 import BeautifulSoup

# Try to import scholar_api for enhancement
try:
    from google_scholar import scholar_api
    SCHOLAR_API_AVAILABLE = True
except ImportError:
    # Handle case where script is run directly from different path
    try:
        import scholar_api
        SCHOLAR_API_AVAILABLE = True
    except ImportError:
        print("Warning: scholar_api module not found. Skipping SerpApi enhancement.")
        SCHOLAR_API_AVAILABLE = False

def get_md5(text):
    return hashlib.md5(text.encode('utf-8')).hexdigest()

def clean_text(text):
    if not text:
        return ""
    # Remove extra whitespace and newlines
    return re.sub(r'\s+', ' ', text).strip()

def parse_scholar_email(html_content):
    soup = BeautifulSoup(html_content, 'html.parser')
    papers = []
    
    # Extract category from footer
    # Pattern: "Google 学术搜索发送此邮件，是因为您关注了 <a ...>XXX</a> 的新搜索结果"
    # We look for the text "Google 学术搜索发送此邮件，是因为您关注了"
    category = "Google Scholar" # Default
    
    # Try to find the specific text node
    target_text = "Google 学术搜索发送此邮件，是因为您关注了"
    found_category = False
    
    # Search in 'p' tags
    for p in soup.find_all('p'):
        p_text = p.get_text()
        if target_text in p_text:
            # Found the paragraph. Now we need to extract the link text.
            a_tag = p.find('a')
            if a_tag:
                cat_text = clean_text(a_tag.get_text())
                # Remove brackets if present (e.g., "[learned "cost model"]")
                if cat_text.startswith('[') and cat_text.endswith(']'):
                    cat_text = cat_text[1:-1].strip()
                
                if cat_text:
                    category = cat_text
                    found_category = True
                    break
    
    # Strategy: Look for the specific structure of Google Scholar alerts
    # Usually: <h3><a ...>Title</a></h3>
    
    for h3 in soup.find_all('h3'):
        a_tag = h3.find('a')
        if not a_tag:
            continue
            
        title = clean_text(a_tag.get_text())
        url = a_tag.get('href')
        
        # Google Scholar redirect URL usually looks like:
        # https://scholar.google.com/scholar_url?url=...
        # We can try to extract the real URL if needed, or just use the redirect.
        # Keeping the redirect is safer as it might be authenticated or tracked, 
        # but for direct access, the real URL is better.
        # Let's keep the original URL for now.
        
        # Authors and snippet
        # They are usually in a div following the h3
        container = h3.parent
        
        # Try to find author div (class 'g-s-a' is common in web, email might vary)
        # We look for the first text node or div after h3
        
        authors_text = ""
        abstract_text = ""
        
        # Iterate siblings
        curr = h3.next_sibling
        while curr:
            if curr.name == 'div':
                txt = clean_text(curr.get_text())
                if not authors_text:
                    authors_text = txt
                else:
                    # If we already have authors, this might be the snippet
                    if txt and len(txt) > 20: # Simple heuristic
                        abstract_text = txt
                        break
            elif curr.name is None: # Text node
                txt = clean_text(str(curr))
                if txt:
                    if not authors_text:
                        authors_text = txt
            
            if curr.name in ['h3', 'hr']: # Stop at next item or separator
                break
                
            curr = curr.next_sibling
            
        # Clean authors
        # Format often: "Author1, Author2... - Journal, Year - Publisher"
        authors_clean = authors_text
        if '-' in authors_text:
            authors_clean = authors_text.split('-')[0].strip()
        
        author_list = [a.strip() for a in authors_clean.split(',') if a.strip()]
        
        # Generate ID
        paper_id = f"scholar_{get_md5(title + ''.join(author_list))}"
        
        # Construct summary for AI
        # If abstract is present, use it. If not, construct a prompt-like summary.
        summary_content = abstract_text if abstract_text else "Abstract not available."
        
        # If abstract is very short or missing, we explicitly include Title and Authors in the summary field
        # to ensure the LLM pays attention to them when generating the report.
        if len(summary_content) < 50:
             final_summary = f"Title: {title}\nAuthors: {', '.join(author_list)}\nAbstract: {summary_content}"
        else:
             final_summary = summary_content

        papers.append({
            "id": paper_id,
            "title": title,
            "authors": author_list,
            "summary": final_summary,
            "categories": [category],
            "pdf": url, 
            "abs": url,
            "comment": "From Google Scholar Alert",
            "source": "Google Scholar"
        })
        
    return papers

def _parse_ymd_date(value):
    return datetime.date.fromisoformat(value.strip())

def _format_imap_date(value):
    months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    return f"{value.day:02d}-{months[value.month - 1]}-{value.year:04d}"

def _resolve_imap_host(email_user, imap_host):
    if imap_host:
        return imap_host
    if email_user and email_user.lower().endswith("@qq.com"):
        return "imap.qq.com"
    return "imap.gmail.com"

def _build_search_criteria(date_since, date_before):
    criteria = ["FROM", "scholaralerts-noreply@google.com"]
    if date_since:
        criteria.extend(["SINCE", _format_imap_date(date_since)])
    if date_before:
        criteria.extend(["BEFORE", _format_imap_date(date_before)])
    return criteria

def fetch_emails(
    email_user,
    email_pass,
    save_path,
    imap_host=None,
    imap_port=993,
    mailbox="INBOX",
    since_date=None,
    before_date=None,
    date=None,
    since_days=1,
):
    if not email_user or not email_pass:
        print("Email credentials (EMAIL_ACCOUNT, EMAIL_APP_PASSWORD) not set. Skipping Google Scholar fetch.")
        return

    print(f"Connecting to IMAP for {email_user}...")
    try:
        resolved_host = _resolve_imap_host(email_user, imap_host)
        mail = imaplib.IMAP4_SSL(resolved_host, int(imap_port))
        mail.login(email_user, email_pass)
        mail.select(mailbox)
        
        if date:
            since_date = date
            before_date = date + datetime.timedelta(days=1)
        elif since_date is None and before_date is None:
            today = datetime.datetime.now(datetime.timezone.utc).date()
            since_date = today - datetime.timedelta(days=int(since_days))
        
        criteria = _build_search_criteria(since_date, before_date)
        
        print(f"Searching emails with criteria: {' '.join(criteria)}")
        typ, data = mail.search(None, *criteria)
        if typ != "OK":
            print(f"IMAP search failed: {typ}")
            mail.close()
            mail.logout()
            return
        
        if not data[0]:
            print("No emails found.")
            mail.close()
            mail.logout()
            return

        all_papers = []
        msg_ids = data[0].split()
        print(f"Found {len(msg_ids)} emails.")
        
        for num in msg_ids:
            try:
                typ, msg_data = mail.fetch(num, '(RFC822)')
                if typ != "OK" or not msg_data or not msg_data[0]:
                    continue
                raw_email = msg_data[0][1]
                msg = email.message_from_bytes(raw_email)
                
                html_content = ""
                if msg.is_multipart():
                    for part in msg.walk():
                        if part.get_content_type() == "text/html":
                            payload = part.get_payload(decode=True)
                            if payload:
                                html_content = payload.decode(errors='ignore')
                            break
                else:
                    if msg.get_content_type() == "text/html":
                        payload = msg.get_payload(decode=True)
                        if payload:
                            html_content = payload.decode(errors='ignore')
                
                if html_content:
                    papers = parse_scholar_email(html_content)
                    msg_id = num.decode() if isinstance(num, (bytes, bytearray)) else str(num)
                    print(f"Parsed {len(papers)} papers from email {msg_id}.")
                    if papers:
                        all_papers.extend(papers)
            except Exception as e:
                print(f"Error parsing email {num}: {e}")
                continue
                
        mail.close()
        mail.logout()
        
        if not all_papers:
            print("No papers extracted from emails.")
            return

        print(f"Total papers found from Google Scholar emails: {len(all_papers)}")
        
        # Enhance papers with SerpApi if available and key is present
        if SCHOLAR_API_AVAILABLE and os.getenv("SERP_API_KEY"):
            print("Enhancing papers with Google Scholar API (SerpApi)...")
            all_papers = scholar_api.enhance_papers_batch(all_papers)
        
        # Append to existing file or create new
        # We use 'a' (append) because arXiv papers might already be there
        # But we must ensure valid JSONL (one JSON per line)
        
        # Check if file exists and ends with newline
        start_newline = False
        if os.path.exists(save_path):
            with open(save_path, 'rb') as f:
                try:
                    f.seek(-1, 2)
                    last = f.read(1)
                    if last != b'\n':
                        start_newline = True
                except OSError:
                    pass # Empty file

        with open(save_path, 'a', encoding='utf-8') as f:
            if start_newline:
                f.write('\n')
            for paper in all_papers:
                f.write(json.dumps(paper, ensure_ascii=False) + '\n')
        
        print(f"Saved Scholar papers to {save_path}")
                
    except Exception as e:
        print(f"Error fetching emails: {e}")
        # We do not exit with error code to avoid breaking the main workflow
        # just because email fetch failed (e.g. auth error, network)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("output", nargs="?", default=None)
    parser.add_argument("--imap-host", default=os.environ.get("IMAP_HOST"))
    parser.add_argument("--imap-port", default=os.environ.get("IMAP_PORT", "993"))
    parser.add_argument("--mailbox", default=os.environ.get("IMAP_MAILBOX", "INBOX"))
    parser.add_argument("--date", default=os.environ.get("EMAIL_DATE"))
    parser.add_argument("--since-date", default=os.environ.get("EMAIL_SINCE_DATE"))
    parser.add_argument("--before-date", default=os.environ.get("EMAIL_BEFORE_DATE"))
    parser.add_argument("--since-days", default=os.environ.get("EMAIL_SINCE_DAYS", "1"))
    args = parser.parse_args()

    email_user = os.environ.get("EMAIL_ACCOUNT")
    email_pass = os.environ.get("EMAIL_APP_PASSWORD")

    save_path = args.output
    if not save_path:
        today = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
        save_path = f"data/{today}.jsonl"

    os.makedirs(os.path.dirname(save_path), exist_ok=True)

    selected_date = _parse_ymd_date(args.date) if args.date else None
    since_date = _parse_ymd_date(args.since_date) if args.since_date else None
    before_date = _parse_ymd_date(args.before_date) if args.before_date else None

    fetch_emails(
        email_user,
        email_pass,
        save_path,
        imap_host=args.imap_host,
        imap_port=int(args.imap_port),
        mailbox=args.mailbox,
        date=selected_date,
        since_date=since_date,
        before_date=before_date,
        since_days=int(args.since_days),
    )
