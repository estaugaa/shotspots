Final deploy for the old Netlify address (shotspots-eric.netlify.app), after Netlify credits reset on Nov 26 2026:
zip index.html + sw.js (+ a `_redirects` with `/* /index.html 200`) and POST once to the Netlify deploys API.
It moves on-device data to the new GitHub Pages address via #import= and retires the old service worker.
