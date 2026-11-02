const {chromium} = require(process.env.PLAYWRIGHT_MODULE || 'C:/Users/santh/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const fs = require('fs');
(async () => {
  const browser = await chromium.launch({headless:true,channel:'msedge',args:['--disable-gpu']});
  const report=[]; const out='.impeccable/review/info'; fs.mkdirSync(out,{recursive:true});
  for (const width of [1440,390]) {
    const page = await browser.newPage({viewport:{width,height:900},reducedMotion:'reduce'});
    const errors=[]; page.on('pageerror',e=>errors.push(e.message));
    for (const route of ['about','contact','privacy']) {
      const response=await page.goto(`http://127.0.0.1:8092/${route}`,{waitUntil:'networkidle'});
      if(response.status()!==200) throw Error(`${route}: ${response.status()}`);
      if(await page.locator('h1').count()!==1) throw Error('Missing page heading');
      if(await page.locator('.info-nav [aria-current="page"]').count()!==1) throw Error('Current page missing');
      if(await page.getByRole('navigation',{name:'Company and privacy'}).getByRole('link').count()!==3) throw Error('Footer links missing');
      const overflow=await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth);
      if(overflow) throw Error(`${route}: horizontal overflow at ${width}`);
      if(route!=='about' && !await page.locator('main a[href^="mailto:rishisugavanam200@gmail.com"]').count()) throw Error('Wrong contact email');
      if(route==='privacy') for(const href of await page.locator('.policy-nav a').evaluateAll(a=>a.map(x=>x.getAttribute('href')))) if(!await page.locator(href).count()) throw Error('Broken policy anchor');
      await page.screenshot({path:`${out}/${route}-${width}.png`,fullPage:true});
      report.push({route,width,status:response.status(),overflow});
    }
    await page.goto('http://127.0.0.1:8092/register',{waitUntil:'networkidle'});
    if(await page.locator('form a[href="/privacy"]').count()!==1) throw Error('Signup privacy notice missing');
    if(errors.length) throw Error(errors.join('; '));
    await page.close();
  }
  fs.writeFileSync('verification/info-pages.json',JSON.stringify(report,null,2));
  console.log(JSON.stringify(report)); await browser.close();
})().catch(e=>{console.error(e);process.exit(1)});
