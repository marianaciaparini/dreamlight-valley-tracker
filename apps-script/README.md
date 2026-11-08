# Optional: sync through your own Google Sheet

Without this, the app saves only in your browser (and iOS may clear that after a few weeks of not opening it). With it, every tick is stored in a Google Sheet you own, and your phone and computer stay in step.

1. Create a new Google Sheet (any name).
2. In the sheet: **Extensions → Apps Script**. Delete what is there and paste the whole of [`Code.gs`](Code.gs).
3. On the line `const SENHA = 'change-me';` replace `change-me` with a password of your own. Save.
4. **Deploy → New deployment →** type **Web app**. Execute as: **Me**. Who has access: **Anyone**. Deploy, and authorise when Google asks.
5. Copy the **Web app URL** (it ends in `/exec`).
6. In the app, open the **Progress** tab → **Connect to my spreadsheet**, paste the URL, then the password. Do this once on each device.

The URL and the password are kept only in that device's browser storage; they are never written into the code.

**Updating the script later:** paste the new code, keep the same password, then **Deploy → Manage deployments → pencil → Version: New version → Deploy**. Do not use "New deployment" again: that creates a different URL, and every device would have to reconnect.

**About "Anyone":** the script must be reachable without a Google login for the page to call it. The password is what stops other people reading or overwriting your data, so pick one you don't use anywhere else. The data is a game tracker; don't store anything sensitive in it.
