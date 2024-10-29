
## Deploy on server
1. Change WEB HOST IP when deploy


## Migrate DB 
flask db upgrade

## How to make migration
flask db migrate -m "logs"


# Fixed list (2024-2-26)
- Lite plan users should see only  venue, and phone, address and website
- Added Mater View mode
- Added URLs list view again for list users
- Change that logic to "x credits remaining"
- Added Copy function in credited data view
- Fix scraping issue for permium/normal users
- Fixed login , signup issue (use only email)
- Fixed the issue that campaign send multi emails at a time. and not working sometimes
- Added new columne to see available credit in admin page
- Added monlty credit column

# Create vapid
npx web-push generate-vapid-keys