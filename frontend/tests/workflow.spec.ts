import {test,expect} from '@playwright/test';

// The mascot introduction has its own tests. Keep workflow tests focused on
// the page controls they exercise, as a real returning visitor would see them.
test.beforeEach(async({page})=>{
 await page.addInitScript(()=>{
  try { localStorage.setItem('skylark.sky.intro.seen.v1','1'); } catch { /* blocked storage is tested below */ }
 });
});

test('workspace switcher shows the available workspace and planned cloud option',async({page})=>{
 await page.goto('/#/app');
 const switcher=page.getByRole('button',{name:'Switch workspace. Current: Local workspace'});
 await switcher.click();
 await expect(switcher).toHaveAttribute('aria-expanded','true');
 const workspaces=page.getByRole('group',{name:'Workspaces'});
 await expect(workspaces.getByRole('button',{name:'Local workspace'})).toHaveAttribute('aria-current','true');
 await expect(workspaces.getByRole('button',{name:'Cloud workspace Coming soon'})).toBeDisabled();
 await page.keyboard.press('Escape');
 await expect(workspaces).toHaveCount(0);
 await expect(switcher).toBeFocused();
 await page.setViewportSize({width:390,height:844});
 await expect(switcher).toBeVisible();
 await switcher.click();
 await expect(workspaces).toBeVisible();
});

test('execution mode names distinguish scripted and paid model evaluations',async({page})=>{
 await page.goto('/#/app');
 const mode=page.getByLabel('Execution mode');
 await expect(mode.locator('option[value="fixture"]')).toHaveText('Scripted evaluation · $0 API cost');
 await expect(mode.locator('option[value="live"]')).toContainText('Model evaluation · API cost applies');
});

test('booking fields define the base task and extra instructions apply only to model evaluations',async({page})=>{
 await page.route('**/api/v1/status',async route=>{
  const response=await route.fetch();
  const status=await response.json();
  await route.fulfill({response,json:{...status,live:{...status.live,enabled:true}}});
 });
 await page.goto('/#/app');
 await expect(page.locator('.scenario-grid')).toHaveCount(0);
 await expect(page.getByRole('textbox',{name:'Resource to book'})).toHaveValue('studio-a');
 await expect(page.getByRole('textbox',{name:'Customer name'})).toHaveValue('Alex');
 await expect(page.getByText('Sandbox item to reserve')).toBeVisible();
 await expect(page.getByText('Name on the reservation')).toBeVisible();
 const message=page.getByRole('textbox',{name:'Additional booking instructions'});
 await expect(message).toBeDisabled();
 await page.getByLabel('Execution mode').selectOption('live');
 await expect(message).toBeEnabled();
 await expect(page.getByText('The base task already asks the agent to make one reservation')).toBeVisible();
 await message.fill('Check the booking outcome before any retry.');
 await page.getByLabel('Execution mode').selectOption('fixture');
 await expect(message).toBeDisabled();
 await expect(message).toHaveValue('Check the booking outcome before any retry.');
 await page.getByRole('button',{name:'Run fixture'}).click();
 await expect(page.getByRole('heading',{name:'Incident',exact:true})).toBeVisible();
 await expect(page.getByRole('alert')).toHaveCount(0);
 await page.setViewportSize({width:390,height:844});
 await page.locator('.sidebar nav').getByRole('button',{name:'Experiments',exact:true}).click();
 expect(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth)).toBeFalsy();
});

test('fixture → incident → reviewed repair → comparison → export survives refresh',async({page})=>{
 await page.goto('/#/app');
 await expect(page.getByRole('heading',{name:'Experiments',exact:true})).toBeVisible();
 await page.screenshot({path:'../.cache/skylark-home.png',fullPage:true});
 await page.getByRole('button',{name:'Run fixture'}).click();
 await expect(page.getByRole('heading',{name:'Incident'})).toBeVisible();
 await expect(page.getByRole('button',{name:'Propose repair'})).toBeEnabled({timeout:60000});
 await expect(page.getByText('Fault delivered',{exact:true})).toBeVisible();
 await expect(page.getByText('res-002',{exact:true}).first()).toBeVisible();
 await page.screenshot({path:'../.cache/skylark-incident.png',fullPage:true});
 await page.reload();
 await page.getByRole('button',{name:/Incident/}).first().click();
 await expect(page.getByText('Fault delivered',{exact:true})).toBeVisible();
 const downloadPromise=page.waitForEvent('download');
 await page.getByRole('link',{name:'Export incident'}).click();
 const download=await downloadPromise;
 expect(download.suggestedFilename()).toMatch(/^skylark-.*\.zip$/);
 await page.getByRole('button',{name:'Propose repair'}).click();
 await expect(page.getByRole('heading',{name:'Repair comparison'})).toBeVisible();
 await page.getByRole('button',{name:'Approve & compare'}).click();
 await expect(page.getByRole('heading',{name:'passed',exact:true})).toBeVisible({timeout:60000});
 await expect(page.getByRole('heading',{name:'failed',exact:true})).toBeVisible();
 await page.screenshot({path:'../.cache/skylark-comparison.png',fullPage:true});
 await page.getByRole('button',{name:/Results/}).first().click();
 await expect(page.getByRole('heading',{name:'Results'})).toBeVisible();
 await expect(page.getByRole('heading',{name:'Outcome dimensions'})).toBeVisible();
 await expect(page.getByText('Accurate report',{exact:true}).first()).toBeVisible();
 const reportDownload=page.waitForEvent('download');
 await page.getByRole('link',{name:'Export results JSON'}).click();
 expect((await reportDownload).suggestedFilename()).toBe('skylark-results.json');
 await page.screenshot({path:'../.cache/skylark-results.png',fullPage:true});
 await page.screenshot({path:'../.cache/skylark-results-overview.png',fullPage:false});
});

test('Results scopes groups, attempts, export and spending to a saved benchmark',async({page})=>{
 const id='a'.repeat(32);
 const selected={id:'b'.repeat(32),status:'completed',created:1,result:{verdict:'passed'},snapshot:{verifier_version:'reservation/5',spec:{mode:'fixture',scenario:{name:'Scoped control',fault:{kind:'none'}},policy:{}}}};
 const checks=Object.fromEntries(['safety','task_completion','reporting_accuracy','fault_coverage'].map(name=>[name,{passed:1,failed:0,unknown:0,not_applicable:name==='fault_coverage'?1:0,observed:1}]));
 const group={id:'group',condition:'none',configuration:'original',model:{id:'test-model'},split:'control',verifier_version:'reservation/5',mode:'fixture',dimensions:checks,total:1,passed:1,failed:0,safe_incomplete:0,inconclusive:0,pending:0,latency_seconds:{median:1},tool_calls:{median:1},accounted_usd:0.001,uncertain_usd:0,unique_scenarios:1,execution_statuses:{completed:1},input_tokens:10,output_tokens:10,provider_requests:1};
 await page.route('**/api/v1/benchmarks',route=>route.fulfill({json:[{id,created:1,mode:'fixture',split:'held_out',run_count:1}]}));
 await page.route(`**/api/v1/results?comparison_id=${id}`,route=>route.fulfill({json:{comparison_id:id,groups:[group],budget:{accounted_usd:0.02,uncertain_usd:0.003}}}));
 await page.route(`**/api/v1/runs?comparison_id=${id}`,route=>route.fulfill({json:[selected]}));
 await page.goto('/#/app');
 await page.getByRole('button',{name:'Results',exact:true}).click();
 const scope=page.getByLabel('Result scope');
 await expect(scope).toContainText('held out · fixture · 1 runs');
 await scope.selectOption(id);
 await expect(page.getByRole('heading',{name:'Protocol attempts'})).toBeVisible();
 await expect(page.getByRole('button',{name:/Scoped control/})).toBeVisible();
 await expect(page.getByText('$0.0010 accounted in this protocol')).toBeVisible();
 await expect(page.getByText('$0.0200 accounted across the whole project')).toBeVisible();
 await expect(page.getByRole('link',{name:'Export results JSON'})).toHaveAttribute('href',`/api/v1/results/export?comparison_id=${id}`);
 await page.reload();
 await page.getByRole('button',{name:'Results',exact:true}).click();
 await expect(scope).toHaveValue(id);
 await expect(page.getByRole('button',{name:/Scoped control/})).toBeVisible();
});

test('polling keeps evidence usable without SSE or the recent-runs entry',async({page})=>{
 await page.route('**/events?stream=true',route=>route.abort());
 await page.goto('/#/app');
 await page.getByRole('button',{name:'Run fixture'}).click();
 await expect(page.getByText('Fault delivered',{exact:true})).toBeVisible({timeout:60000});
 await expect(page.getByText('DELIVERED TO AGENT',{exact:true}).first()).toBeVisible();
 await page.route('**/api/v1/runs',route=>route.request().method()==='GET'?route.fulfill({json:[]}):route.continue());
 await page.reload();
 await page.getByRole('button',{name:'Incident',exact:true}).click();
 await expect(page.getByText('Fault delivered',{exact:true})).toBeVisible();
 await expect(page.getByText('res-002',{exact:true}).first()).toBeVisible();
});

test('settings keyboard focus stays in dialog and returns on Escape',async({page})=>{
 await page.goto('/#/app');
 const trigger=page.getByRole('button',{name:'Connection and budget',exact:true});
 await trigger.click();
 const close=page.getByRole('button',{name:'Close settings'});
 await expect(close).toBeFocused();
 await page.keyboard.press('Shift+Tab');
 await expect(page.getByRole('button',{name:'Done'})).toBeFocused();
 await page.keyboard.press('Tab');
 await expect(close).toBeFocused();
 await page.keyboard.press('Escape');
 await expect(page.getByRole('dialog')).toHaveCount(0);
 await expect(trigger).toBeFocused();
});

test('narrow-screen layout and local setup',async({page})=>{
 await page.setViewportSize({width:390,height:844});
 await page.goto('/#/app');
 await expect(page.getByRole('button',{name:'Run fixture'})).toBeVisible();
 const overflow=await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth);
 expect(overflow).toBeFalsy();
 await page.getByRole('button',{name:'About',exact:true}).click();
 await expect(page.getByRole('heading',{name:'About Skylark'})).toBeVisible();
 await expect(page.getByRole('img',{name:'Choose fault, run agent, inspect incident, review repair, verify and export'})).toBeVisible();
 await page.screenshot({path:'../.cache/skylark-about-mobile.png',fullPage:true});
 await expect(page.getByRole('heading',{name:'Evidence modes'})).toBeVisible();
 expect(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth)).toBeFalsy();
 await page.setViewportSize({width:1191,height:668});
 expect(await page.locator('.circuit-scroll').evaluate(element=>element.scrollWidth>element.clientWidth)).toBeFalsy();
 await page.getByRole('button',{name:'Experiments',exact:true}).click();
 await expect(page.getByRole('button',{name:'Run fixture'})).toBeVisible();
});

test('reports load on demand and completed incidents stop polling',async({page})=>{
 let reports=0,incidentReads=0;
 page.on('request',request=>{
  if(new URL(request.url()).pathname==='/api/v1/results')reports++;
  if(/\/runs\/[^/]+(?:\/events)?$/.test(new URL(request.url()).pathname)&&request.method()==='GET')incidentReads++;
 });
 await page.goto('/#/app');
 await expect(page.getByRole('button',{name:'Run fixture'})).toBeEnabled();
 expect(reports).toBe(0);
 await page.getByRole('button',{name:'Run fixture'}).click();
 await expect(page.getByRole('button',{name:'Propose repair'})).toBeEnabled({timeout:60000});
 await expect(page.getByText('verification',{exact:true})).toBeVisible();
 // Allow the terminal drain to finish, then observe a former polling interval.
 await page.waitForTimeout(500);
 const completedReads=incidentReads;
 await page.waitForTimeout(2500);
 expect(incidentReads).toBe(completedReads);
 expect(reports).toBe(0);
 await page.getByRole('button',{name:'Results',exact:true}).click();
 await expect(page.getByText('Accurate report',{exact:true}).first()).toBeVisible();
 expect(reports).toBeGreaterThan(0);
});

test('retrying a lost submission response reuses its experiment identity',async({page})=>{
 const keys:string[]=[];
 let createdId='';
 await page.route('**/api/v1/runs',async route=>{
  if(route.request().method()!=='POST'){await route.continue();return}
  keys.push(route.request().headers()['idempotency-key']);
  const response=await route.fetch();
  const result=await response.json();
  if(keys.length===1){createdId=result.id;await route.abort('failed')}
  else{expect(result.id).toBe(createdId);await route.fulfill({response})}
 });
 await page.goto('/#/app');
 await page.getByRole('button',{name:'Run fixture'}).click();
 await expect(page.getByRole('alert')).toBeVisible();
 await expect(page.getByRole('button',{name:'Run fixture'})).toBeEnabled({timeout:60000});
 await page.getByRole('button',{name:'Run fixture'}).click();
 await expect(page.getByRole('heading',{name:'Incident'})).toBeVisible();
 expect(keys).toHaveLength(2);expect(keys[0]).toBe(keys[1]);
});

test('validation errors explain the invalid field',async({page})=>{
 await page.goto('/#/app');
 await page.getByLabel('Resource',{exact:true}).fill('INVALID RESOURCE');
 await page.getByRole('button',{name:'Run fixture'}).click();
 await expect(page.getByRole('alert')).toContainText('scenario.resource');
 await expect(page.getByRole('alert')).not.toContainText('[object Object]');
});

test('location history supports back, forward, and a new navigation branch',async({page})=>{
 await page.goto('/#/app');
 const back=page.getByRole('button',{name:'Go back',exact:true});
 const forward=page.getByRole('button',{name:'Go forward',exact:true});
 await expect(back).toHaveCount(0);await expect(forward).toHaveCount(0);
 await expect(page.getByRole('group',{name:'Page history'})).toHaveCount(0);
 await page.getByRole('button',{name:'About',exact:true}).click();
 await page.getByRole('button',{name:'Results',exact:true}).click();
 await back.click();
 await expect(page.getByRole('heading',{name:'About Skylark'})).toBeVisible();
 await forward.click();
 await expect(page.getByRole('heading',{name:'Results',exact:true})).toBeVisible();
 await back.click();
 await page.getByRole('button',{name:'About',exact:true}).click();
 await expect(forward).toBeEnabled();
 await page.getByRole('button',{name:'Repair comparison',exact:true}).click();
 await expect(forward).toHaveCount(0);
 await back.click();
 await expect(page.getByRole('heading',{name:'About Skylark'})).toBeVisible();
});

test('settings preferences persist and apply without changing live execution',async({page})=>{
 await page.goto('/#/app');
 await page.getByRole('button',{name:'Settings',exact:true}).click();
 const dialog=page.getByRole('dialog',{name:'Settings',exact:true});
 await dialog.getByRole('button',{name:'Appearance',exact:true}).click();
 await dialog.getByLabel('Animated wordmark').uncheck();
 await dialog.getByLabel('Compact experiment tables').check();
 await dialog.getByRole('button',{name:'Experiment defaults',exact:true}).click();
 await dialog.getByLabel('Default customer').fill('Taylor');
 await dialog.getByRole('button',{name:'Done',exact:true}).click();
 await page.reload();
 await expect(page.getByLabel('Customer',{exact:true})).toHaveValue('Taylor');
 await expect(page.locator('.shell')).toHaveClass(/no-shine/);
 await expect(page.locator('.shell')).toHaveClass(/compact-tables/);
 await expect(page.getByLabel('Execution mode')).toHaveValue('fixture');
});

test('landing opens the workbench and fits mobile',async({page})=>{
 await page.emulateMedia({reducedMotion:'reduce'});
 await page.goto('/');
 await expect(page.getByRole('heading',{name:'Tools fail. Your agent should recover.'})).toBeVisible();
 await page.screenshot({path:'../.cache/skylark-landing.png',fullPage:true});
 await page.setViewportSize({width:390,height:844});
 expect(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth)).toBeFalsy();
 await page.screenshot({path:'../.cache/skylark-landing-mobile.png',fullPage:true});
 await page.getByRole('link',{name:'Get Started',exact:true}).click();
 await expect(page.getByRole('button',{name:'Run fixture'})).toBeVisible();
 await page.reload();
 await expect(page.getByRole('button',{name:'Run fixture'})).toBeVisible();
});

test('particle wordmark appears only on About and loads near the viewport',async({page})=>{
 const requests:string[]=[];
 page.on('request',request=>{if(request.url().includes('InteractiveParticles-'))requests.push(request.url())});
 await page.goto('/');
 await expect(page.getByRole('img',{name:'SKYLARK — interactive particle wordmark'})).toHaveCount(0);
 await page.getByRole('link',{name:'Get Started',exact:true}).click();
 await expect(page.getByRole('img',{name:'SKYLARK — interactive particle wordmark'})).toHaveCount(0);
 expect(requests).toHaveLength(0);
 await page.getByRole('button',{name:'About',exact:true}).click();
 const particleRequest=page.waitForRequest(request=>request.url().includes('InteractiveParticles-'));
 await page.getByRole('img',{name:'SKYLARK — interactive particle wordmark'}).scrollIntoViewIfNeeded();
 await particleRequest;
});

test('landing slideshow, FAQ, and creator credit work',async({page})=>{
 await page.emulateMedia({reducedMotion:'reduce'});
 await page.goto('/');
 const carousel=page.getByRole('region',{name:'How Skylark works'});
 await carousel.getByRole('button',{name:'Next →',exact:true}).click();
 await expect(carousel.getByRole('heading',{name:'A timeout is not a rollback.'})).toBeVisible();
 await carousel.getByRole('button',{name:/04.*Verify recovery/}).click();
 await expect(carousel.getByRole('link',{name:'Try the demo'})).toBeVisible();
 const question=page.getByRole('button',{name:/Do I need an API key/});
 await question.click();await expect(question).toHaveAttribute('aria-expanded','true');
 await expect(page.getByText('No. The scripted fixture runs locally', {exact:false})).toBeVisible();
 await question.click();await expect(question).toHaveAttribute('aria-expanded','false');
 await expect(page.getByLabel('Built with love for Agents by Ankit Shrivastava')).toBeVisible();
 await page.setViewportSize({width:390,height:844});
 expect(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth)).toBeFalsy();
 await page.screenshot({path:'../.cache/skylark-landing-sections.png',fullPage:true});
});

test('theme persists across app and landing and follows system changes',async({page})=>{
 await page.emulateMedia({colorScheme:'light',reducedMotion:'reduce'});
 await page.goto('/#/app');
 await page.getByRole('button',{name:'Settings',exact:true}).click();
 await page.getByRole('button',{name:'Appearance',exact:true}).click();
 await page.getByLabel('Theme',{exact:true}).selectOption('dark');
 await expect(page.locator('html')).toHaveAttribute('data-theme','dark');
 await page.screenshot({path:'../.cache/skylark-dark-settings.png'});
 await page.getByRole('button',{name:'Done',exact:true}).click();
 await page.screenshot({path:'../.cache/skylark-dark-app.png'});
 await page.reload();
 await expect(page.locator('html')).toHaveAttribute('data-theme','dark');
 await page.locator('a.brand').click();
 await expect(page.getByRole('link',{name:'Get Started',exact:true})).toBeVisible();
 await expect(page.locator('html')).toHaveAttribute('data-theme','dark');
 await page.screenshot({path:'../.cache/skylark-dark-landing.png',fullPage:true});
 await page.getByRole('link',{name:'Get Started',exact:true}).click();
 await page.getByRole('button',{name:'Settings',exact:true}).click();
 await page.getByRole('button',{name:'Appearance',exact:true}).click();
 await page.getByLabel('Theme',{exact:true}).selectOption('system');
 await expect(page.locator('html')).toHaveAttribute('data-theme','light');
 await page.emulateMedia({colorScheme:'dark'});
 await expect(page.locator('html')).toHaveAttribute('data-theme','dark');
 await page.getByLabel('Theme',{exact:true}).selectOption('light');
 await expect(page.locator('html')).toHaveAttribute('data-theme','light');
});

test('navigation help appears after two seconds and dismisses without navigating',async({page})=>{
 await page.goto('/#/app');
 await page.getByRole('button',{name:'Experiments',exact:true}).hover({position:{x:8,y:8}});
 await page.waitForTimeout(1100);
 await expect(page.getByRole('tooltip')).toHaveCount(0);
 await expect(page.getByRole('tooltip')).toContainText('Choose a scenario',{timeout:2500});
 await page.keyboard.press('Escape');
 await expect(page.getByRole('tooltip')).toHaveCount(0);
 await page.getByRole('button',{name:'Results',exact:true}).locator('.cursor-help-label').hover();
 await expect(page.getByRole('tooltip')).toContainText('Review safety',{timeout:3000});
 await page.mouse.move(600,50);
 await expect(page.getByRole('tooltip')).toHaveCount(0);
 await expect(page.getByRole('heading',{name:'Experiments',exact:true})).toBeVisible();
});

test('sidebar icons stay visible while images load or fail',async({page})=>{
 await page.setViewportSize({width:390,height:844});
 let releaseImages!:()=>void;
 const imagesReady=new Promise<void>(resolve=>{releaseImages=resolve});
 await page.route('**/assets/*.png',async route=>{
  if(route.request().url().includes('results-chart-'))return route.abort();
  await imagesReady;
  return route.continue();
 });
 await page.goto('/#/app',{waitUntil:'domcontentloaded'});
 const icons=page.locator('.sidebar nav .nav-icon-slot');
 await expect(icons).toHaveCount(5);
 await expect(icons.locator('svg')).toHaveCount(5);
 releaseImages();
 await expect(icons.locator('img.is-loaded')).toHaveCount(4);
 await expect(icons.locator('svg')).toHaveCount(1);
 await expect(icons.nth(3).locator('svg')).toBeVisible();
});

test('workbench remains usable when browser storage is blocked',async({page})=>{
 await page.addInitScript(()=>Object.defineProperty(window,'localStorage',{
  configurable:true,
  get(){throw new DOMException('Storage blocked','SecurityError')},
 }));
 await page.goto('/#/app');
 await expect(page.getByRole('button',{name:'Run fixture'})).toBeEnabled();
 await page.getByRole('button',{name:'Run fixture'}).click();
 await expect(page.getByRole('heading',{name:'Incident'})).toBeVisible();
 await expect(page.getByRole('button',{name:'Propose repair'})).toBeEnabled({timeout:60000});
 await page.getByRole('button',{name:'Propose repair'}).click();
 await expect(page.getByRole('heading',{name:'Repair comparison'})).toBeVisible();
});
