import warnings
import os
import sys
import tomllib
import yaml
import argparse
import logging
import requests 

# Suppress pydantic warnings from ATProto
warnings.filterwarnings("ignore", module="pydantic")
warnings.filterwarnings("ignore", message=".*The 'default' attribute with value None.*")

from dotenv import load_dotenv
from atproto import Client, models
from mastodon import Mastodon

# --- CONFIGURATION ---
load_dotenv()

BASE_URL = os.getenv("BASE_URL")

# Bluesky configuration
BSKY_HANDLE = os.getenv("BSKY_HANDLE")
BSKY_PASSWORD = os.getenv("BSKY_PASSWORD")
BSKY_CHAR_LIMIT = 290

# Mastodon configuration
MASTODON_ACCESS_TOKEN = os.getenv("MASTODON_ACCESS_TOKEN")
MASTODON_API_BASE = os.getenv("MASTODON_API_BASE")
MASTODON_CHAR_LIMIT = 490 

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

# --- Content Handling ---
def parse_frontmatter(content):
    try:
        if content.startswith("+++"):
            end = content.find("+++", 3)
            return tomllib.loads(content[3:end])
        elif content.startswith("---"):
            end = content.find("---", 3)
            return yaml.safe_load(content[3:end])
    except Exception as e:
        logging.error(f"Parsing error: {e}")
    return None

def get_post_url(filepath, frontmatter):
    """
    Constructs the public URL.
    Handles nested folders (content/blog/2025/11/post.md) correctly.
    """
    root = BASE_URL if BASE_URL else "https://example.com"
    root = root.rstrip("/")
    
    # Normalize path separators to forward slashes for consistency
    path_norm = os.path.normpath(filepath).replace("\\", "/")
    path_parts = path_norm.split("/")
    
    try:
        # Find 'content' and capture everything after it
        content_idx = path_parts.index("content")
        # e.g. ['blog', '2025', '11']
        dirs = path_parts[content_idx + 1 : -1]
    except ValueError:
        dirs = ["posts"] # Fallback

    filename = os.path.basename(filepath)
    
    # Handle "Leaf Bundles" (folders with index.md)
    if filename == "index.md" or filename == "_index.md":
        if frontmatter.get("slug"):
            dirs[-1] = frontmatter.get("slug")
        url_path = "/".join(dirs)
    else:
        # Standard File
        slug = frontmatter.get("slug")
        if not slug:
            slug = os.path.splitext(filename)[0]
        url_path = "/".join(dirs + [slug])

    return f"{root}/{url_path}/"

def verify_url_accessible(url):
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (SyndicationScript)'}
        response = requests.get(url, headers=headers, timeout=10)
        return response.status_code == 200
    except requests.exceptions.RequestException as e:
        logging.error(f"Connection failed for {url}: {e}")
        return False

def truncate_text(title, content, limit, suffix=""):
    """Truncates content ot fit limits, ensuring suffix is never chopped (for Mastodon)."""
    suffix_padding = 2 if suffix else 0
    reserved_chars = len(title) + 2 + len(suffix) + suffix_padding 
    available_chars = limit - reserved_chars
    
    if available_chars <= 0:
        return f"{title[:limit-len(forced_suffix)-5]}... {forced_suffix}"
        
    final_content = ""
    if content:
        if len(content) > available_chars:
            final_content = f"{content[:available_chars-3]}..."
        else:
            final_content = content
    
    parts = [title]
    if final_content:
        parts.append(final_content)
    if forced_suffix:
        parts.append(forced_suffix)
        
    return "\n\n".join(parts)

# --- Syndication ---
def syndicate_to_bluesky(client, frontmatter, url):
    if not client: return False
    
    title = frontmatter.get("title", "New Post")
    text_content = frontmatter.get("microblog_content", "")
    
    post_text = truncate_text(title, text_content, BSKY_CHAR_LIMIT)
    
    external = models.AppBskyEmbedExternal.External(
        title=title,
        description=text_content[:200],
        uri=url,
        thumb=None 
    )
    embed_card = models.AppBskyEmbedExternal.Main(external=external)
    
    try:
        client.send_post(text=post_text, embed=embed_card)
        logging.info(f"✅ Bluesky: Posted '{title}'")
        return True
    except Exception as e:
        logging.error(f"❌ Bluesky Failed: {e}")
        return False

def syndicate_to_mastodon(client, frontmatter, url):
    if not client: return False

    title = frontmatter.get("title", "New Post")
    text_content = frontmatter.get("microblog_content", "")
    
    # Reserve chars for the URL
    limit = MASTODON_CHAR_LIMIT - len(url) - 2
    post_text = truncate_text(title, text_content, limit)
    
    final_text = f"{post_text}\n\n{url}"

    try:
        client.status_post(status=final_text)
        logging.info(f"✅ Mastodon: Posted '{title}'")
        return True
    except Exception as e:
        logging.error(f"❌ Mastodon Failed: {e}")
        return False

def mark_syndicated(manifest_item):
    filepath = manifest_item["filepath"]
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            lines = f.readlines()
        
        # Detect format based on the first line
        is_toml = lines[0].strip() == "+++"
        delimiter = "+++" if is_toml else "---"
        
        # Set the correct syntax for the boolean
        # TOML uses '=', YAML uses ':'
        syndicated_line = "syndicated = true\n" if is_toml else "syndicated: true\n"
        
        with open(filepath, "w", encoding="utf-8") as f:
            found_closing = False
            for i, line in enumerate(lines):
                # Look for the CLOSING delimiter (not the first one)
                if i > 0 and line.strip() == delimiter and not found_closing:
                    f.write(syndicated_line) # Insert valid syntax
                    f.write(line)
                    found_closing = True
                else:
                    f.write(line)
                    
        logging.info(f"💾 Updated syndicated status in {filepath}")
    except Exception as e:
        logging.error(f"Error marking syndicated: {e}")

def main():
    parser = argparse.ArgumentParser(description="Syndicate Hugo blog posts.")
    parser.add_argument("content_dir", help="The directory containing Hugo content.")
    parser.add_argument("--dry-run", action="store_true", help="Simulate syndication.")
    parser.add_argument("--force", action="store_true", help="Skip URL verification.")
    args = parser.parse_args()

    # --- CLIENT INIT ---
    bsky_client = None
    masto_client = None
    
    if not args.dry_run:
        has_bsky_creds = all([BSKY_HANDLE, BSKY_PASSWORD])
        has_masto_creds = all([MASTODON_ACCESS_TOKEN, MASTODON_API_BASE])

        if not has_bsky_creds and not has_masto_creds:
            logging.critical("CRITICAL: No credentials found for Bluesky OR Mastodon.")
            sys.exit(1)

        if has_bsky_creds:
            try:
                bsky_client = Client()
                bsky_client.login(BSKY_HANDLE, BSKY_PASSWORD)
                logging.info("Connected to Bluesky.")
            except Exception as e:
                logging.error(f"Bluesky Connection Error: {e}")

        if has_masto_creds:
            try:
                masto_client = Mastodon(access_token=MASTODON_ACCESS_TOKEN, api_base_url=MASTODON_API_BASE)
                logging.info("Connected to Mastodon.")
            except Exception as e:
                logging.error(f"Mastodon Connection Error: {e}")
    else:
        logging.info("--- DRY RUN MODE ACTIVE ---")

    manifest = []
    
    # --- SCANNING ---
    for root, dirs, files in os.walk(args.content_dir):
        for file in files:
            if file.endswith(".md"):
                filepath = os.path.join(root, file)
                try:
                    with open(filepath, "r", encoding="utf-8") as f:
                        content = f.read()
                        fm = parse_frontmatter(content)
                        
                        if fm and "syndicate_to" in fm:
                            if fm.get("syndicated", False):
                                continue
                            
                            if not fm.get("microblog_content"):
                                logging.warning(f"SKIPPED {file}: Missing 'microblog_content'.")
                                continue
                                
                            manifest.append({"frontmatter": fm, "filepath": filepath})
                except Exception as e:
                    logging.warning(f"Could not read {file}: {e}")

    logging.info(f"Found {len(manifest)} post(s) ready to syndicate.")

    # --- PROCESSING ---
    for item in manifest:
        title = item['frontmatter'].get('title', 'Unknown')
        url = get_post_url(item['filepath'], item['frontmatter'])
        targets = item['frontmatter'].get('syndicate_to', [])
        
        # 1. URL VERIFICATION
        if not args.dry_run and not args.force:
            logging.info(f"Verifying URL: {url}")
            if not verify_url_accessible(url):
                logging.critical(f"STOPPING: URL {url} is not accessible.")
                continue

        # 2. EXECUTION
        results = []
        
        if "bluesky" in targets:
            if args.dry_run:
                print(f"[Bluesky Dry Run] {title} -> {url}")
                results.append(True)
            elif bsky_client:
                results.append(syndicate_to_bluesky(bsky_client, item['frontmatter'], url))
            else:
                results.append(False)

        if "mastodon" in targets:
            if args.dry_run:
                print(f"[Mastodon Dry Run] {title} -> {url}")
                results.append(True)
            elif masto_client:
                results.append(syndicate_to_mastodon(masto_client, item['frontmatter'], url))
            else:
                results.append(False)

        # 3. MARK SYNDICATED
        if len(results) > 0 and all(results):
            if args.dry_run:
                print(f"ACTION: Would mark {os.path.basename(item['filepath'])} as syndicated.\n")
            else:
                mark_syndicated(item)
        elif not args.dry_run and len(results) > 0:
            logging.warning(f"⚠️ Partial failure for {title}. Not marking as syndicated.")

if __name__ == "__main__":
    main()