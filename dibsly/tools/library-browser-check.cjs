const {chromium}=require(process.env.PLAYWRIGHT_MODULE || 'C:/Users/santh/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const fs=require('fs');
(async()=>{
  const browser=await chromium.launch({headless:true,channel:'msedge',args:['--disable-gpu']});
  const out='.impeccable/review/library';fs.mkdirSync(out,{recursive:true});const results=[];
  for(const width of [1440,390]){
    const page=await browser.newPage({viewport:{width,height:900},reducedMotion:'reduce'});const errors=[];
    page.on('pageerror',e=>errors.push(e.message));
    await page.goto('http://127.0.0.1:8092/login');
    await page.getByLabel('Username',{exact:true}).fill('admin');await page.getByLabel('Password',{exact:true}).fill('DibslyAdmin2026!');
    await page.getByRole('button',{name:'Log in',exact:true}).click();await page.waitForURL('**/app/dashboard');
    const response=await page.goto('http://127.0.0.1:8092/app/access',{waitUntil:'networkidle'});
    if(response.status()!==200)throw Error('Access lab failed');
    if(!await page.getByRole('heading',{name:'Powered by Safe Revoke 1.0.0.'}).isVisible())throw Error('Library not identified');
    const overflow=await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth);
    if(overflow)throw Error('Body overflow at '+width);
    await page.screenshot({path:`${out}/access-${width}.png`});
    const table=page.getByRole('table');const text=await table.innerText();
    if(!text.includes('revision')||!text.includes('ACCESS_ALLOWED'))throw Error('Library decisions missing');
    await page.getByRole('heading',{name:'Safe Revoke audit trail'}).scrollIntoViewIfNeeded();
    await page.evaluate(()=>{const h=Array.from(document.querySelectorAll('h2')).find(x=>x.textContent==='Safe Revoke audit trail');window.scrollTo(0,h.getBoundingClientRect().top+scrollY-24);});
    await page.screenshot({path:`${out}/audit-${width}.png`});
    if(errors.length)throw Error(errors.join('; '));
    results.push({width,status:response.status(),overflow,library:'Safe Revoke 1.0.0',versionedAudit:true,errors});await page.close();
  }
  fs.writeFileSync('verification/library-browser.json',JSON.stringify(results,null,2));console.log(JSON.stringify(results));await browser.close();
})().catch(e=>{console.error(e);process.exit(1)});
