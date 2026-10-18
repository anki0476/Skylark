import {test,expect} from '@playwright/test';

test('fixture → incident → reviewed repair → comparison → export survives refresh',async({page})=>{
 await page.goto('/');
 await expect(page.getByRole('heading',{name:'Find the failure. Prove the recovery.'})).toBeVisible();
 await page.screenshot({path:'../.cache/skylark-home.png',fullPage:true});
 await page.getByRole('button',{name:'Run fixture'}).click();
 await expect(page.getByRole('heading',{name:'Inside the incident'})).toBeVisible();
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
 await expect(page.getByRole('heading',{name:'A repair earns its result.'})).toBeVisible();
 await page.getByRole('button',{name:'Approve & compare'}).click();
 await expect(page.getByRole('heading',{name:'passed',exact:true})).toBeVisible({timeout:60000});
 await expect(page.getByRole('heading',{name:'failed',exact:true})).toBeVisible();
 await page.screenshot({path:'../.cache/skylark-comparison.png',fullPage:true});
 await page.getByRole('button',{name:/Results/}).first().click();
 await expect(page.getByRole('heading',{name:'Evidence, without the spin.'})).toBeVisible();
 await expect(page.getByRole('heading',{name:'Outcome dimensions'})).toBeVisible();
 await expect(page.getByText('Ready to experiment',{exact:true})).toBeVisible();
 await expect(page.getByText('Accurate report',{exact:true}).first()).toBeVisible();
 const reportDownload=page.waitForEvent('download');
 await page.getByRole('link',{name:'Download results JSON'}).click();
 expect((await reportDownload).suggestedFilename()).toBe('skylark-results.json');
 await page.screenshot({path:'../.cache/skylark-results.png',fullPage:true});
 await page.screenshot({path:'../.cache/skylark-results-overview.png',fullPage:false});
});

test('polling keeps evidence usable without SSE or the recent-runs entry',async({page})=>{
 await page.route('**/events?stream=true',route=>route.abort());
 await page.goto('/');
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
 await page.goto('/');
 const trigger=page.getByRole('button',{name:'Connection and budget',exact:true});
 await trigger.click();
 const close=page.getByRole('button',{name:'Close settings'});
 await expect(close).toBeFocused();
 await page.keyboard.press('Shift+Tab');
 await expect(page.getByRole('button',{name:'Back to the lab'})).toBeFocused();
 await page.keyboard.press('Tab');
 await expect(close).toBeFocused();
 await page.keyboard.press('Escape');
 await expect(page.getByRole('dialog')).toHaveCount(0);
 await expect(trigger).toBeFocused();
});

test('narrow-screen layout and local setup',async({page})=>{
 await page.setViewportSize({width:390,height:844});
 await page.goto('/');
 await expect(page.getByRole('button',{name:'Run fixture'})).toBeVisible();
 const overflow=await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth);
 expect(overflow).toBeFalsy();
});

test('reports load on demand and completed incidents stop polling',async({page})=>{
 let reports=0,incidentReads=0;
 page.on('request',request=>{
  if(new URL(request.url()).pathname==='/api/v1/results')reports++;
  if(/\/runs\/[^/]+(?:\/events)?$/.test(new URL(request.url()).pathname)&&request.method()==='GET')incidentReads++;
 });
 await page.goto('/');
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
 await page.goto('/');
 await page.getByRole('button',{name:'Run fixture'}).click();
 await expect(page.getByRole('alert')).toBeVisible();
 await expect(page.getByRole('button',{name:'Run fixture'})).toBeEnabled({timeout:60000});
 await page.getByRole('button',{name:'Run fixture'}).click();
 await expect(page.getByRole('heading',{name:'Inside the incident'})).toBeVisible();
 expect(keys).toHaveLength(2);expect(keys[0]).toBe(keys[1]);
});

test('validation errors explain the invalid field',async({page})=>{
 await page.goto('/');
 await page.getByLabel('Resource',{exact:true}).fill('INVALID RESOURCE');
 await page.getByRole('button',{name:'Run fixture'}).click();
 await expect(page.getByRole('alert')).toContainText('scenario.resource');
 await expect(page.getByRole('alert')).not.toContainText('[object Object]');
});
