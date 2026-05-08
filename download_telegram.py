import requests
import re
import os
import sys
from urllib.parse import urlparse, unquote
from bs4 import BeautifulSoup

def download_telegram_post(post_url):
    """Download media and text from a SPECIFIC Telegram post only"""

    # Convert to preview URL
    if '/s/' not in post_url:
        post_url = post_url.replace('t.me/', 't.me/s/')

    print(f"[+] Fetching: {post_url}")

    # Get the page
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }
    response = requests.get(post_url, headers=headers)

    if response.status_code != 200:
        print(f"[-] Failed to fetch post. Status: {response.status_code}")
        return

    soup = BeautifulSoup(response.content, 'html.parser')

    # Extract channel name and post ID
    match = re.search(r't\.me/s?/([^/]+)/(\d+)', post_url)
    if match:
        channel_name = match.group(1)
        post_id = match.group(2)
    else:
        channel_name = "telegram"
        post_id = "post"

    # Create folder structure: downloads/channel_name/post_id/
    folder = os.path.join("downloads", channel_name, post_id)
    os.makedirs(folder, exist_ok=True)
    print(f"[+] Saving to folder: {folder}/")

    # Find the SPECIFIC post message div (not all posts on page!)
    # This ensures we only get files from THIS post
    post_div = soup.find('div', {'class': 'tgme_widget_message', 'data-post': f"{channel_name}/{post_id}"})

    if not post_div:
        # Fallback: try to find the message by looking for the post link
        all_messages = soup.find_all('div', class_='tgme_widget_message')
        for msg in all_messages:
            msg_link = msg.find('a', class_='tgme_widget_message_date')
            if msg_link and post_id in msg_link.get('href', ''):
                post_div = msg
                break

    if not post_div:
        print("[-] Could not find the specific post on the page")
        print("[!] Trying to download from entire page (may get extra files)")
        post_div = soup
    else:
        print(f"[+] Found specific post #{post_id}")

    # Extract text content from THIS post only
    text_div = post_div.find('div', class_='tgme_widget_message_text')
    if text_div:
        text = text_div.get_text(strip=True)
        with open(f"{folder}/post_text.txt", 'w', encoding='utf-8') as f:
            f.write(text)
        print(f"[+] Saved text content")

    # Find media elements ONLY in this specific post
    downloaded_count = 0

    # Try to find video in THIS post
    video = post_div.find('video')
    if video and video.get('src'):
        video_url = video['src']
        if not video_url.startswith('http'):
            video_url = 'https://telegram.org' + video_url
        filename = download_file(video_url, folder, 'video.mp4')
        if filename:
            downloaded_count += 1
            print(f"[+] Downloaded video: {filename}")

    # Try to find images in THIS post
    images = post_div.find_all('a', class_='tgme_widget_message_photo_wrap')
    for idx, img in enumerate(images):
        style = img.get('style', '')
        match = re.search(r"url\('([^']+)'\)", style)
        if match:
            img_url = match.group(1)
            filename = download_file(img_url, folder, f'image_{idx}.jpg')
            if filename:
                downloaded_count += 1
                print(f"[+] Downloaded image: {filename}")

    # Try to find document/file downloads in THIS post
    documents = post_div.find_all('a', class_='tgme_widget_message_document_wrap')
    for idx, doc in enumerate(documents):
        doc_link = doc.get('href')
        if doc_link:
            # Extract filename from the document title
            title_elem = doc.find('div', class_='tgme_widget_message_document_title')
            if title_elem:
                filename = title_elem.get_text(strip=True)
            else:
                filename = f'document_{idx}'

            downloaded_file = download_file(doc_link, folder, filename)
            if downloaded_file:
                downloaded_count += 1
                print(f"[+] Downloaded document: {downloaded_file}")

    if downloaded_count == 0:
        print("[!] No media files found in this post")

    print(f"\n[✓] Complete! Downloaded {downloaded_count} file(s) to {folder}/")
    return folder

def download_file(url, folder, filename):
    """Download a file from URL"""
    try:
        if not url.startswith('http'):
            url = 'https://telegram.org' + url

        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Referer': 'https://t.me/'
        }

        response = requests.get(url, headers=headers, stream=True, timeout=30)

        if response.status_code != 200:
            return None

        # Clean filename
        filename = re.sub(r'[<>:"/\\|?*]', '_', filename)
        filepath = os.path.join(folder, filename)

        with open(filepath, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)

        return filename
    except Exception as e:
        print(f"[-] Error downloading {url}: {str(e)}")
        return None

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python download_telegram.py <telegram_post_url>")
        sys.exit(1)

    post_url = sys.argv[1]
    download_telegram_post(post_url)
