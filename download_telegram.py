import requests
import re
import os
import sys
from urllib.parse import urlparse, unquote
from bs4 import BeautifulSoup

def download_telegram_post(post_url):
    """Download media and text from a Telegram post"""

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

    # Create folder
    folder = f"{channel_name}_{post_id}"
    os.makedirs(folder, exist_ok=True)
    print(f"[+] Saving to folder: {folder}/")

    # Extract text content
    text_div = soup.find('div', class_='tgme_widget_message_text')
    if text_div:
        text = text_div.get_text(strip=True)
        with open(f"{folder}/post_text.txt", 'w', encoding='utf-8') as f:
            f.write(text)
        print(f"[+] Saved text content")

    # Find all media elements
    downloaded_count = 0

    # Try to find video
    video = soup.find('video')
    if video and video.get('src'):
        video_url = video['src']
        if not video_url.startswith('http'):
            video_url = 'https://telegram.org' + video_url
        filename = download_file(video_url, folder, 'video.mp4')
        if filename:
            downloaded_count += 1
            print(f"[+] Downloaded video: {filename}")

    # Try to find images
    images = soup.find_all('a', class_='tgme_widget_message_photo_wrap')
    for idx, img in enumerate(images):
        style = img.get('style', '')
        match = re.search(r"url\('([^']+)'\)", style)
        if match:
            img_url = match.group(1)
            filename = download_file(img_url, folder, f'image_{idx}.jpg')
            if filename:
                downloaded_count += 1
                print(f"[+] Downloaded image: {filename}")

    # Try to find document/file downloads
    documents = soup.find_all('a', class_='tgme_widget_message_document_wrap')
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

    # Try alternative: look for direct download links
    download_links = soup.find_all('a', href=re.compile(r'https://[^"]*\.(mp3|mp4|zip|pdf|rar|7z|doc|docx|xls|xlsx|ppt|pptx)'))
    for link in download_links:
        url = link['href']
        filename = os.path.basename(urlparse(url).path)
        filename = unquote(filename)
        downloaded_file = download_file(url, folder, filename)
        if downloaded_file:
            downloaded_count += 1
            print(f"[+] Downloaded file: {downloaded_file}")

    # Try to find any iframe or embed with file
    iframes = soup.find_all('iframe')
    for iframe in iframes:
        src = iframe.get('src')
        if src and any(ext in src for ext in ['.mp3', '.mp4', '.zip', '.pdf']):
            filename = os.path.basename(urlparse(src).path)
            downloaded_file = download_file(src, folder, filename)
            if downloaded_file:
                downloaded_count += 1
                print(f"[+] Downloaded from iframe: {downloaded_file}")

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
