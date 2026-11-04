import {readFileSync,writeFileSync,mkdirSync,copyFileSync} from 'node:fs';
const custom=process.env.THESMIO_CUSTOM_DOMAIN==='true';
const origin=custom?'https://thesmio.gr':'https://donacgreece.github.io/thesmio';
const prefix=custom?'/':'/thesmio/';
const filepath='dist/index.html';
let html=readFileSync(filepath,'utf8').replaceAll('https://donacgreece.github.io/thesmio/',origin+'/');
writeFileSync(filepath,html);
writeFileSync('dist/robots.txt',`User-agent: *\nAllow: /\nSitemap: ${origin}/sitemap.xml\n`);
const pages=['','?page=laws','?page=members','?page=parties','?page=votes','?page=control','?page=documents','?page=stats','?page=sources'];
writeFileSync('dist/sitemap.xml',`<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">${pages.map(p=>`<url><loc>${origin}/${p? p.replace('&','&amp;') : ''}</loc></url>`).join('')}</urlset>`);
// SPA fallback for direct URLs under Pages project path.
copyFileSync(filepath,'dist/404.html');
if(custom){writeFileSync('dist/CNAME','thesmio.gr');}
console.log(`Built for ${origin} (base ${prefix})`);
