// Rebuilds the iPhone app (index.html, sw.js, manifest) from data/trip.json. No dependencies: `node tools/build.js`.
const fs = require('fs'), path = require('path'), crypto = require('crypto');
const ROOT = path.join(__dirname, '..'), T = f => path.join(__dirname, f), O = f => path.join(ROOT, f);
const data = JSON.parse(fs.readFileSync(O('data/trip.json'), 'utf8'));
const tpl = fs.readFileSync(T('template.html'), 'utf8');
const css = tpl.match(/<style id="app-style">([\s\S]*?)<\/style>/)[1];
const reset = fs.readFileSync(T('reset.css'), 'utf8');
const js = tpl.match(/<script id="app-script">([\s\S]*?)<\/script>/)[1].replace('"__RESET__"', JSON.stringify(reset));
const LS = String.fromCharCode(0x2028), PS = String.fromCharCode(0x2029);
const json = JSON.stringify(data).replace(/</g, '\\u003c').split(LS).join('\\u2028').split(PS).join('\\u2029');
const ver = crypto.createHash('sha1').update(json + js + css).digest('hex').slice(0, 10);
const html = '<!doctype html><html lang="en"><head><meta charset="utf-8">' +
  '<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover"><title>Japan Trip</title>\n' +
  '<meta name="apple-mobile-web-app-capable" content="yes"><meta name="mobile-web-app-capable" content="yes">' +
  '<meta name="apple-mobile-web-app-title" content="Japan Trip"><meta name="apple-mobile-web-app-status-bar-style" content="default">\n' +
  '<meta name="theme-color" content="#f3f5f9" media="(prefers-color-scheme: light)"><meta name="theme-color" content="#0c111d" media="(prefers-color-scheme: dark)">' +
  '<meta name="robots" content="noindex,nofollow">\n' +
  '<link rel="apple-touch-icon" href="apple-touch-icon.png"><link rel="icon" href="apple-touch-icon.png"><link rel="manifest" href="manifest.webmanifest">\n' +
  '<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>\n' +
  '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Atkinson+Hyperlegible:ital,wght@0,400;0,700;1,400&family=BIZ+UDPGothic:wght@400;700&display=swap">\n' +
  '<style>' + reset + '</style>\n<style id="app-style">' + css + '</style></head><body>\n' +
  '<div id="app"></div><div id="layer"></div>\n' +
  '<script type="application/json" id="trip-data">' + json + '</script>\n' +
  '<script id="app-script">' + js + '</script>\n' +
  '<script>if("serviceWorker"in navigator)addEventListener("load",function(){navigator.serviceWorker.register("sw.js").catch(function(){})})</script>\n</body></html>\n';
fs.writeFileSync(O('index.html'), html);
fs.writeFileSync(O('sw.js'), fs.readFileSync(T('sw.tpl.js'), 'utf8').replace('__VER__', ver));
fs.writeFileSync(O('manifest.webmanifest'), JSON.stringify({
  name: 'Japan Trip Nov 2026', short_name: 'Japan Trip', start_url: './', scope: './', display: 'standalone',
  background_color: '#f3f5f9', theme_color: '#1d3a8f',
  icons: [{ src: 'apple-touch-icon.png', sizes: '180x180', type: 'image/png' }]
}));
// Claude-app copy (view-only page body for the Artifact at claude.ai/artifact/28vtak4L17FNue2WPbvhC6)
const ai = process.argv.indexOf('--artifact');
if (ai > 0) {
  fs.writeFileSync(process.argv[ai + 1], '<title>' + data.title + '</title>\n' +
    '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Atkinson+Hyperlegible:ital,wght@0,400;0,700;1,400&family=BIZ+UDPGothic:wght@400;700&display=swap">\n' +
    '<style id="app-style">' + css + '</style>\n<div id="app"></div><div id="layer"></div>\n' +
    '<script type="application/json" id="trip-data">' + json + '</script>\n<script id="app-script">' + js + '</script>\n');
}
console.log('built version', ver, '·', data.days.reduce((n, d) => n + d.items.length, 0), 'stops ·', Object.keys(data.places).length, 'places ·', data.todo.length, 'to-dos');
