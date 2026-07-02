from dotenv import load_dotenv
from pathlib import Path
from datetime import datetime, UTC
import os, requests

load_dotenv()
SHOP = os.getenv('RESIN_SHOPIFY_STORE_DOMAIN') or os.getenv('SHOPIFY_STORE_DOMAIN')
TOKEN = os.getenv('RESIN_SHOPIFY_ADMIN_ACCESS_TOKEN') or os.getenv('SHOPIFY_ADMIN_ACCESS_TOKEN')
VERSION = os.getenv('SHOPIFY_API_VERSION','2026-01')
THEME_ID = os.getenv('RESIN_SHOPIFY_THEME_ID') or os.getenv('SHOPIFY_THEME_ID')
HEADERS = {'X-Shopify-Access-Token': TOKEN, 'Content-Type': 'application/json'}
ROOT = Path(__file__).resolve().parent
backup_dir = ROOT / 'theme-backups'
backup_dir.mkdir(exist_ok=True)

if not THEME_ID:
    themes_url = f'https://{SHOP}/admin/api/{VERSION}/themes.json'
    themes_res = requests.get(themes_url, headers=HEADERS, timeout=30)
    print('GET themes', themes_res.status_code)
    themes_res.raise_for_status()
    main_theme = next((theme for theme in themes_res.json()['themes'] if theme.get('role') == 'main'), None)
    if not main_theme:
        raise RuntimeError('Could not find the published Shopify theme.')
    THEME_ID = str(main_theme['id'])
    print('Using published theme', THEME_ID, main_theme.get('name'))

BASE = f'https://{SHOP}/admin/api/{VERSION}/themes/{THEME_ID}/assets.json'

res = requests.get(BASE, headers=HEADERS, params={'asset[key]':'layout/theme.liquid'}, timeout=30)
print('GET theme.liquid', res.status_code)
res.raise_for_status()
asset = res.json()['asset']
content = asset['value']
backup_path = backup_dir / f"theme.liquid.before-resin-chatwoot.{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}.liquid"
backup_path.write_text(content, encoding='utf-8')

snippet = (ROOT / 'shopify-resin-chatwoot-widget.liquid').read_text(encoding='utf-8').strip()
marker = 'Resin Society Chatwoot Website Chat'
if marker in content:
    print('Widget already present; no Shopify update needed.')
    print('backup', backup_path)
    raise SystemExit(0)
if '</body>' not in content:
    raise RuntimeError('Could not find </body> in layout/theme.liquid')
updated = content.replace('</body>', snippet + '\n</body>', 1)
put = requests.put(BASE, headers=HEADERS, json={'asset': {'key': 'layout/theme.liquid', 'value': updated}}, timeout=30)
print('PUT theme.liquid', put.status_code)
put.raise_for_status()
print('backup', backup_path)
print('installed', marker in updated)

