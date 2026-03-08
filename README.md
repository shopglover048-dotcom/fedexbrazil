# FedEx Delivery Platform (Offline Static Build)

This project runs as plain HTML/CSS/JavaScript with no Python server.

## How to run
1. Open `index.html` in your browser.
2. Use `ship.html` to create a shipment.
3. Use `track.html?id=YOUR_TRACKING_ID` to view tracking.
4. Press `Ctrl + Shift + A` from any page to open admin login.
5. After login, use `admin.html` for admin actions.

## Data storage
- All shipment/admin data is stored in browser `localStorage` and `sessionStorage`.
- Data is local to the browser profile on your device.
- Clearing browser storage removes saved shipments.

## Admin login (offline defaults)
- Username: `admin`
- Password: `admin`
- Login check is case-insensitive (capless).

## Hidden Admin Access
- Admin login is hidden from normal page navigation.
- Use keyboard shortcut `Ctrl + Shift + A` to open it.

## Notes
- No backend, no Flask routes, no SQLite database required for this static mode.
- World map geocoding and map tiles still require internet access to OpenStreetMap services.
