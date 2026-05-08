#!/usr/bin/env python3
import os, json, subprocess, re, urllib.parse, hashlib, glob, time, sys

MAX_SIZE_MB = 80
PASSWORD = os.environ.get('PASSWORD', '')
REPO = os.environ.get('GITHUB_REPOSITORY', '')
BRANCH = os.environ.get('GITHUB_REF_NAME', 'main')
LINKS_INPUT = os.environ.get('TELEGRAM_LINKS', '')

raw = LINKS_INPUT
links = list(dict.fromkeys([l.strip() for l in re.split(r'[,\s\n]+', raw) if l.strip().startswith('http')]))
print(f"📋 Found {len(links)} link(s)")

def safe_name(name):
    base, ext = os.path.splitext(name)
    if not ext: ext = '.bin'
    safe = re.sub(r'[^a-zA-Z0-9._-]', '_', base)[:50] or hashlib.md5(name.encode()).hexdigest()[:12]
    return f"{safe}{ext.lower()}"

def get_remote_size(url):
    """Get file size from server before downloading"""
    try:
        headers = ['-H', 'User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36']
        r = subprocess.run(['curl', '-sI', '-L', '--max-time', '30'] + headers + [url],
            capture_output=True, text=True, timeout=35)
        for line in r.stdout.split('\n'):
            if line.lower().startswith('content-length:'):
                size = int(line.split(':')[1].strip())
                return size
    except:
        pass
    return None

def resolve(link):
    headers = ['-H', 'User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36']

    print("  🔍 Trying telegramdownloader.net...")
    try:
        r = subprocess.run(['curl', '-s', '--max-time', '30', '-X', 'POST'] + headers + [
            '-H', 'Content-Type: application/x-www-form-urlencoded',
            '-H', 'Origin: https://telegramdownloader.net',
            '-H', 'Referer: https://telegramdownloader.net/',
            '-d', f'telegram_link={urllib.parse.quote(link)}',
            'https://telegramdownloader.net/proxy.php'], capture_output=True, text=True, timeout=35)
        if r.returncode == 0 and r.stdout:
            data = json.loads(r.stdout)
            url = data.get('data', {}).get('data', {}).get('link')
            name = data.get('data', {}).get('data', {}).get('file_name')
            size = data.get('data', {}).get('data', {}).get('file_size')
            if url:
                print(f"  ✅ Resolved! Size: {size or 'unknown'}")
                return url, name, size
    except Exception as e:
        print(f"  ⚠️ Error: {e}")

    print("  🔍 Trying tgsave.com...")
    try:
        r = subprocess.run(['curl', '-s', '--max-time', '30', '-X', 'POST'] + headers + [
            '-H', 'Content-Type: application/json',
            '-H', 'Origin: https://tgsave.com',
            '-H', 'Referer: https://tgsave.com/',
            '-d', json.dumps({"url": link}),
            'https://api.tgsave.com/download'], capture_output=True, text=True, timeout=35)
        if r.returncode == 0 and r.stdout:
            data = json.loads(r.stdout)
            url = data.get('url') or data.get('link') or data.get('download_url')
            name = data.get('filename') or data.get('file_name')
            size = data.get('size') or data.get('file_size')
            if url:
                print(f"  ✅ Resolved! Size: {size or 'unknown'}")
                return url, name, size
    except Exception as e:
        print(f"  ⚠️ Error: {e}")

    print("  🔍 Trying direct CDN...")
    try:
        r = subprocess.run(['curl', '-sL', '--max-time', '20', '-w', '\n%{url_effective}'] + headers + [link],
            capture_output=True, text=True, timeout=25)
        if r.returncode == 0:
            lines = r.stdout.split('\n')
            final_url = lines[-1] if lines else ''
            
            if 'telesco.pe/file/' in final_url or 'telegram.org/file/' in final_url:
                name = urllib.parse.unquote(final_url.split('/')[-1].split('?')[0])
                print(f"  ✅ Found CDN link via redirect!")
                return final_url, name, None
            
            cdn_patterns = [
                r'https://cdn[0-9]*\.telesco\.pe/file/[a-zA-Z0-9_-]+',
                r'https://[^"<>\s]*telegram\.org/file/[^"<>\s]+',
            ]
            for pattern in cdn_patterns:
                match = re.search(pattern, r.stdout)
                if match:
                    url = match.group(0)
                    if len(url) > 50:
                        name = urllib.parse.unquote(url.split('/')[-1].split('?')[0])
                        print(f"  ✅ Found CDN link in HTML!")
                        print(f"  ⚠️ Warning: Direct CDN links may require authentication")
                        return url, name, None
    except Exception as e:
        print(f"  ⚠️ Error: {e}")

    print("  ❌ All resolvers failed")
    return None, None, None

def is_valid_file(path, min_size_kb=100, expected_bytes=None):
    if not os.path.exists(path):
        return False, "File not found"

    actual_size = os.path.getsize(path)
    size_kb = actual_size / 1024

    try:
        with open(path, 'rb') as f:
            header = f.read(2048).lower()
            
            if size_kb < 50:
                preview = header[:200].decode('utf-8', errors='ignore')
                print(f"    🔍 File preview (first 200 chars): {preview}")
            
            if b'<!doctype' in header or b'<html' in header:
                return False, "HTML error page"
            if b'{"error"' in header or b'"error":' in header:
                return False, "JSON error response"
            if b'access denied' in header or b'forbidden' in header:
                return False, "Access denied"
            if b'not found' in header and size_kb < 100:
                return False, "404 Not Found"
            if b'<error>' in header or b'<message>' in header:
                return False, "XML error response"
    except Exception as e:
        print(f"    ⚠️ Content check error: {e}")

    try:
        r = subprocess.run(['file', '--mime-type', '-b', path], capture_output=True, text=True, timeout=10)
        mime = r.stdout.strip()
        print(f"    🔍 MIME type: {mime}")
        if mime in ['text/html', 'text/plain', 'application/json'] and size_kb < 500:
            return False, f"Invalid type: {mime}"
    except:
        pass

    if size_kb < min_size_kb:
        return False, f"Too small ({size_kb:.1f} KB, expected >{min_size_kb} KB)"

    if expected_bytes and actual_size < expected_bytes * 0.95:
        return False, f"Incomplete download ({actual_size}/{expected_bytes} bytes, {actual_size*100/expected_bytes:.1f}%)"

    return True, "OK"

def download(url, path, expected_size=None):
    for f in glob.glob(f"{path}*.aria2"):
        try: os.remove(f)
        except: pass

    remote_size = get_remote_size(url)
    if remote_size:
        print(f"    📏 Expected size: {remote_size / (1024*1024):.1f} MB")

    min_kb = 100
    expected_bytes = remote_size
    if expected_size and not remote_size:
        try:
            size_str = str(expected_size).lower()
            if 'gb' in size_str:
                expected_bytes = int(float(re.search(r'[\d.]+', size_str).group()) * 1024 * 1024 * 1024)
            elif 'mb' in size_str:
                expected_bytes = int(float(re.search(r'[\d.]+', size_str).group()) * 1024 * 1024)
            elif 'kb' in size_str:
                expected_bytes = int(float(re.search(r'[\d.]+', size_str).group()) * 1024)
            min_kb = expected_bytes / 1024 * 0.9 if expected_bytes else 100
        except:
            pass

    headers = [
        '-H', 'User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        '-H', 'Accept: */*',
        '-H', 'Referer: https://t.me/'
    ]

    print(f"    🔍 Checking URL accessibility...")
    try:
        check_result = subprocess.run(['curl', '-sI', '-L', '--max-time', '10', '-w', '%{http_code}'] + headers + [url],
            capture_output=True, text=True, timeout=15)
        http_code = check_result.stdout.strip().split('\n')[-1]
        print(f"    📡 HTTP Status: {http_code}")
        if http_code.startswith('4') or http_code.startswith('5'):
            print(f"    ⚠️ Server returned error status {http_code}")
    except:
        pass

    methods = [
        ('aria2c', ['aria2c', '-x4', '-s4', '-k1M', '--max-tries=5', '--retry-wait=3',
            '--timeout=300', '--connect-timeout=30', '--allow-overwrite=true',
            '--file-allocation=none', '--continue=false', '--auto-file-renaming=false',
            '--max-connection-per-server=4', '--split=4', '--min-split-size=1M',
            '--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            '--header=Referer: https://t.me/',
            '-d', os.path.dirname(path), '-o', os.path.basename(path), url]),
        ('curl', ['curl', '-L', '-S', '--max-time', '3600', '--retry', '5',
            '--retry-delay', '3', '--retry-max-time', '1800', '--retry-all-errors',
            '-w', '\nHTTP_CODE:%{http_code}'] + headers + ['-o', path, url]),
        ('wget', ['wget', '--timeout=300', '--tries=5', '--wait=3', '--random-wait',
            '--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            '--referer=https://t.me/', '-O', path, url])
    ]

    for name, cmd in methods:
        for attempt in range(1, 3):
            print(f"    🔄 Trying {name} (attempt {attempt}/2)...")
            try:
                if os.path.exists(path): os.remove(path)

                if attempt > 1:
                    time.sleep(2)

                result = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)

                if name == 'curl' and result.stderr:
                    http_match = re.search(r'HTTP_CODE:(\d+)', result.stderr)
                    if http_match:
                        http_code = http_match.group(1)
                        print(f"    📡 HTTP Response: {http_code}")

                if result.returncode != 0:
                    print(f"    ⚠️ {name} exit code: {result.returncode}")
                    if result.stderr:
                        stderr_preview = result.stderr[:500].strip()
                        if stderr_preview:
                            print(f"    ⚠️ Error output: {stderr_preview}")

                for f in glob.glob(f"{path}*.aria2"):
                    try: os.remove(f)
                    except: pass

                if os.path.exists(path):
                    actual_size = os.path.getsize(path)
                    print(f"    📦 Downloaded: {actual_size / (1024*1024):.2f} MB")

                    is_valid, reason = is_valid_file(path, min_kb, expected_bytes)
                    if is_valid:
                        size_mb = actual_size / (1024*1024)
                        print(f"    ✅ Success! ({size_mb:.1f} MB)")
                        return True
                    else:
                        print(f"    ⚠️ Invalid: {reason}")
                        if "Incomplete" in reason and attempt < 2:
                            print(f"    🔄 Retrying same method...")
                            continue
                        elif attempt == 2:
                            print(f"    ⏭️ Moving to next method...")
                        try:
                            os.remove(path)
                        except:
                            pass
                else:
                    print(f"    ⚠️ No file created by {name}")

            except subprocess.TimeoutExpired:
                print(f"    ⚠️ {name} timed out after 1 hour")
            except Exception as e:
                print(f"    ⚠️ Exception: {type(e).__name__}: {e}")

            break

    print(f"    ❌ All download methods failed")
    return False

results = []
for idx, link in enumerate(links, 1):
    print(f"\n{'='*50}")
    print(f"📥 [{idx}/{len(links)}] {link[:60]}...")
    print(f"{'='*50}")

    url, name, expected_size = resolve(link)
    if not url:
        print("  ❌ Failed to resolve")
        continue

    print(f"  🔗 Download URL: {url[:80]}...")

    name = safe_name(name or url.split('/')[-1].split('?')[0] or f"file_{idx}")
    folder = os.path.splitext(name)[0]

    base_folder = folder
    counter = 1
    while os.path.exists(f"downloads/{folder}"):
        folder = f"{base_folder}_{counter}"
        counter += 1

    os.makedirs(f"downloads/{folder}", exist_ok=True)
    filepath = f"downloads/{folder}/{name}"

    print(f"  📁 Folder: {folder}")
    print(f"  📄 File: {name}")

    if download(url, filepath, expected_size):
        size_mb = os.path.getsize(filepath) / (1024*1024)
        results.append({'name': name, 'folder': folder, 'link': link, 'size': size_mb})
        print(f"  ✅ Downloaded!")
    else:
        print(f"  ❌ Failed to download after all attempts")
        try: os.rmdir(f"downloads/{folder}")
        except: pass

print(f"\n{'='*50}")
print(f"📦 Processing files...")
print(f"{'='*50}")

ARCHIVES = {'.zip', '.rar', '.7z', '.gz', '.xz', '.tar', '.tgz', '.bz2'}

for r in results:
    folder, name = r['folder'], r['name']
    filepath = f"downloads/{folder}/{name}"
    if not os.path.exists(filepath): continue

    size_mb = os.path.getsize(filepath) / (1024*1024)
    ext = os.path.splitext(name)[1].lower()
    base = os.path.splitext(name)[0]
    parts = []
    is_archive = ext in ARCHIVES

    orig_dir = os.getcwd()
    os.chdir(f"downloads/{folder}")

    if is_archive:
        if size_mb > MAX_SIZE_MB:
            print(f"  ✂️ Splitting archive {name} ({size_mb:.1f} MB) into {MAX_SIZE_MB}MB volumes...")

            cmd = ['7z', 'a', '-v' + str(MAX_SIZE_MB) + 'm', '-mx0']
            if PASSWORD:
                cmd += ['-p' + PASSWORD, '-mhe=on']
                print(f"  🔐 Adding password protection...")
            cmd += [f'{name}.7z', name]

            result = subprocess.run(cmd, capture_output=True, text=True)

            volume_files = sorted([f for f in os.listdir('.') if f.startswith(f'{name}.7z.')])

            if volume_files:
                os.remove(name)
                parts = volume_files
                print(f"  ✅ Split into {len(parts)} volumes")
            elif os.path.exists(f'{name}.7z'):
                os.remove(name)
                parts.append(f'{name}.7z')
                print(f"  ✅ Created {name}.7z")
            else:
                print(f"  ⚠️ 7z failed, keeping original")
                parts.append(name)
        else:
            print(f"  📦 Keeping archive {name} as-is ({size_mb:.1f} MB)")
            parts.append(name)

    else:
        if size_mb > MAX_SIZE_MB:
            print(f"  ✂️ Splitting {name} ({size_mb:.1f} MB) into {MAX_SIZE_MB}MB volumes...")

            cmd = ['7z', 'a', '-v' + str(MAX_SIZE_MB) + 'm', '-mx1']
            if PASSWORD:
                cmd += ['-p' + PASSWORD, '-mhe=on']
                print(f"  🔐 Adding password protection...")
            cmd += [f'{base}.7z', name]

            result = subprocess.run(cmd, capture_output=True, text=True)

            volume_files = sorted([f for f in os.listdir('.') if f.startswith(f'{base}.7z.')])

            if volume_files:
                os.remove(name)
                parts = volume_files
                print(f"  ✅ Split into {len(parts)} volumes")
            elif os.path.exists(f'{base}.7z'):
                os.remove(name)
                parts.append(f'{base}.7z')
                print(f"  ✅ Created {base}.7z")
            else:
                print(f"  ⚠️ 7z failed, keeping original")
                parts.append(name)

        elif PASSWORD:
            print(f"  🔐 Creating password-protected archive for {name}...")
            cmd = ['7z', 'a', '-p' + PASSWORD, '-mhe=on', f'{base}.7z', name]
            subprocess.run(cmd, capture_output=True)
            if os.path.exists(f'{base}.7z'):
                os.remove(name)
                parts.append(f'{base}.7z')
                print(f"  ✅ Created encrypted {base}.7z")
            else:
                parts.append(name)

        else:
            print(f"  📄 Keeping {name} as-is ({size_mb:.1f} MB)")
            parts.append(name)

    for f in glob.glob('*.aria2'):
        try: os.remove(f)
        except: pass

    os.chdir(orig_dir)
    r['parts'] = parts

print(f"\n📝 Generating READMEs...")
for r in results:
    folder = r['folder']
    raw_base = f"https://github.com/{REPO}/raw/refs/heads/{BRANCH}/downloads/{urllib.parse.quote(folder)}"

    lines = [f"# 📄 {r['name']}", "", f"📦 **Original Size:** {r['size']:.1f} MB", ""]

    is_split = len(r.get('parts', [])) > 1 or any('.7z.' in p for p in r.get('parts', []))

    if is_split:
        lines.append(f"⚠️ **This file was split into {len(r['parts'])} volumes due to GitHub size limits.**")
        lines.append("")
        lines.append("## 📥 Download ALL Volumes")
        lines.append("")
        for p in r.get('parts', []):
            url = f"{raw_base}/{urllib.parse.quote(p)}"
            part_path = f"downloads/{folder}/{p}"
            if os.path.exists(part_path):
                part_size = os.path.getsize(part_path) / (1024*1024)
                lines.append(f"- [{p}]({url}) ({part_size:.1f} MB)")
            else:
                lines.append(f"- [{p}]({url})")

        orig_name = r['name']
        first_vol = r['parts'][0] if r['parts'] else f'{orig_name}.7z.001'
        lines += [
            "",
            "## 🔧 How to Extract",
            "",
            "**Download ALL volumes to the same folder, then extract using 7-Zip:**",
            "",
            "### Using 7-Zip (Recommended - works on all platforms):",
            "```bash",
            "# Install 7-Zip first, then:",
            f"7z x '{first_vol}'",
            "```",
            "",
            "### Windows:",
            "1. Install [7-Zip](https://www.7-zip.org/)",
            f"2. Right-click on `{first_vol}` → 7-Zip → Extract Here",
            "",
            "### Mac:",
            "```bash",
            "brew install p7zip",
            f"7z x '{first_vol}'",
            "```",
            "",
            "### Linux:",
            "```bash",
            "sudo apt install p7zip-full  # or: yum install p7zip",
            f"7z x '{first_vol}'",
            "```"
        ]
    else:
        lines.append("## 🔗 Download")
        lines.append("")
        for p in r.get('parts', [r['name']]):
            url = f"{raw_base}/{urllib.parse.quote(p)}"
            lines.append(f"- 📥 [{p}]({url})")

    lines += ["", "---", f"📎 Source: [Telegram]({r['link']})"]

    with open(f"downloads/{folder}/README.md", 'w') as f:
        f.write('\n'.join(lines))

with open('downloads/README.md', 'w') as f:
    f.write("# 📥 Downloads\n\n")
    f.write("| 📄 File | 📦 Size | 📁 Folder | Volumes |\n")
    f.write("|---------|---------|----------|--------|\n")
    for r in results:
        parts_count = len(r.get('parts', []))
        parts_str = f"{parts_count} volumes" if parts_count > 1 else "1 file"
        f.write(f"| {r['name']} | {r['size']:.1f} MB | [{r['folder']}](./{urllib.parse.quote(r['folder'])}) | {parts_str} |\n")
    f.write("\n⚠️ **Note:** Files larger than 80MB are split into 7z volumes. Download ALL volumes and extract with 7-Zip. See individual folder READMEs for instructions.\n")

for f in glob.glob('downloads/**/*.aria2', recursive=True):
    try: os.remove(f)
    except: pass

print(f"\n{'='*50}")
print(f"✅ Completed: {len(results)} file(s)")
print(f"{'='*50}")
