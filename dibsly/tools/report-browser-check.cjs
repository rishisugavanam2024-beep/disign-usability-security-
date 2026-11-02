const {chromium}=require(process.env.PLAYWRIGHT_MODULE || 'C:/Users/santh/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const fs=require('fs');
(async()=>{
  const browser=await chromium.launch({headless:true,channel:'msedge',args:['--disable-gpu']});
  const output='.local/reports';fs.mkdirSync(output,{recursive:true});const results=[];
  try {
    for(const width of [1440,390]) {
      const page=await browser.newPage({viewport:{width,height:900},reducedMotion:'reduce'});
      const errors=[];page.on('pageerror',error=>errors.push(error.message));
      await page.goto('http://127.0.0.1:8092/login');
      await page.getByLabel('Username',{exact:true}).fill('admin');
      await page.getByLabel('Password',{exact:true}).fill('DibslyAdmin2026!');
      await page.getByRole('button',{name:'Log in',exact:true}).click();
      await page.waitForURL('**/app/dashboard');
      await page.goto('http://127.0.0.1:8092/app/access');
      const link=page.getByRole('link',{name:'Download denied-action report (CSV)',exact:true});
      await link.scrollIntoViewIfNeeded();
      const heading=page.getByRole('heading',{name:'Safe Revoke audit trail',exact:true});
      await heading.evaluate(el=>window.scrollTo(0,el.getBoundingClientRect().top+scrollY-30));
      const overflow=await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth);
      if(overflow)throw Error('Body overflows at '+width);
      await page.screenshot({path:`${output}/report-${width}.png`});
      const [download]=await Promise.all([page.waitForEvent('download'),link.click()]);
      if(await download.failure())throw Error(await download.failure());
      const file=`${output}/browser-denials-${width}.csv`;await download.saveAs(file);
      const report=fs.readFileSync(file,'utf8');
      if(!report.startsWith('library_version,event_id,occurred_at_utc,')||!report.includes('ACCESS_DENIED'))throw Error('Invalid report download');
      if(errors.length)throw Error(errors.join('; '));
      results.push({width,bodyOverflow:overflow,download:download.suggestedFilename(),csvBytes:Buffer.byteLength(report),errors});
      await page.close();
    }
    fs.writeFileSync('verification/report-browser.json',JSON.stringify(results,null,2));console.log(JSON.stringify(results));
  } finally {await browser.close();}
})().catch(error=>{console.error(error);process.exit(1)});
